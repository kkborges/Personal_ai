"""
services/bluetooth_service.py — Gerenciamento Bluetooth completo
Suporta: caixas de som, fones, TVs, sistemas veiculares, multimedia devices
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from config import settings
from database.db import get_db
from models.schemas import BluetoothDevice, BluetoothDeviceType, BluetoothScanResult

logger = logging.getLogger(__name__)

# Tenta importar bleak (BLE), mas não falha se não disponível
try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    logger.warning("bleak não instalado - Bluetooth BLE via simulação")

# Identificadores de fabricantes/perfis para classificar dispositivos
DEVICE_CLASSIFIERS = {
    "jbl": BluetoothDeviceType.speaker,
    "bose": BluetoothDeviceType.speaker,
    "sony wh": BluetoothDeviceType.headphone,
    "sony wf": BluetoothDeviceType.headphone,
    "airpods": BluetoothDeviceType.headphone,
    "samsung tv": BluetoothDeviceType.tv,
    "lg oled": BluetoothDeviceType.tv,
    "pioneer": BluetoothDeviceType.car_audio,
    "kenwood": BluetoothDeviceType.car_audio,
    "alpine": BluetoothDeviceType.car_audio,
    "motorola": BluetoothDeviceType.phone,
    "samsung galaxy": BluetoothDeviceType.phone,
    "iphone": BluetoothDeviceType.phone,
    "xiaomi": BluetoothDeviceType.multimedia,
    "chromecast": BluetoothDeviceType.multimedia,
    "fire tv": BluetoothDeviceType.multimedia,
    "apple tv": BluetoothDeviceType.multimedia,
    "roku": BluetoothDeviceType.multimedia,
}


class BluetoothService:
    """Serviço de gerenciamento Bluetooth com suporte a múltiplos tipos de dispositivos."""

    def __init__(self):
        self._connected: Dict[str, Any] = {}   # mac -> device info
        self._scan_cache: List[BluetoothDevice] = []
        self._scanning = False
        self._trusted: List[str] = []
        self._active_call_device: Optional[str] = None

    async def initialize(self):
        """Inicializa e carrega dispositivos confiáveis."""
        trusted_str = settings.trusted_devices
        if trusted_str:
            try:
                self._trusted = json.loads(trusted_str)
            except Exception:
                pass

        # Carrega do banco
        db = await get_db()
        cur = await db.execute("SELECT mac_address FROM bluetooth_devices WHERE trusted=1")
        rows = await cur.fetchall()
        for r in rows:
            if r["mac_address"] not in self._trusted:
                self._trusted.append(r["mac_address"])

        logger.info(f"✅ BluetoothService inicializado. {len(self._trusted)} dispositivos confiáveis.")

    async def scan(self, duration: int = None) -> BluetoothScanResult:
        """Escaneia dispositivos Bluetooth próximos."""
        duration = duration or settings.bluetooth_scan_duration
        self._scanning = True
        devices = []

        if BLEAK_AVAILABLE:
            try:
                discovered = await BleakScanner.discover(timeout=duration)
                for d in discovered:
                    dtype = self._classify_device(d.name or "")
                    dev = BluetoothDevice(
                        mac_address=d.address,
                        name=d.name,
                        device_type=dtype,
                        trusted=d.address in self._trusted,
                        rssi=getattr(d, 'rssi', None),
                        last_seen=datetime.utcnow(),
                    )
                    devices.append(dev)
                    await self._save_device(dev)
            except Exception as e:
                logger.error(f"BLE scan error: {e}")
        else:
            # Simulação para desenvolvimento/teste
            devices = self._mock_scan()

        self._scan_cache = devices
        self._scanning = False
        logger.info(f"Bluetooth scan: {len(devices)} dispositivos encontrados")
        return BluetoothScanResult(
            devices=devices,
            scan_duration=duration,
            total_found=len(devices)
        )

    async def connect(self, mac_address: str) -> Dict[str, Any]:
        """Conecta a um dispositivo Bluetooth."""
        if mac_address in self._connected:
            return {"status": "already_connected", "mac": mac_address}

        device_info = next((d for d in self._scan_cache if d.mac_address == mac_address), None)

        if BLEAK_AVAILABLE:
            try:
                client = BleakClient(mac_address)
                await asyncio.wait_for(client.connect(), timeout=15)
                if client.is_connected:
                    self._connected[mac_address] = {
                        "client": client,
                        "name": device_info.name if device_info else "Unknown",
                        "type": device_info.device_type if device_info else "unknown",
                        "connected_at": datetime.utcnow().isoformat(),
                    }
                    await self._update_last_conn(mac_address)
                    return {"status": "connected", "mac": mac_address, "name": device_info.name if device_info else "Unknown"}
            except asyncio.TimeoutError:
                return {"status": "timeout", "mac": mac_address}
            except Exception as e:
                return {"status": "error", "mac": mac_address, "error": str(e)}
        else:
            # Simulação
            self._connected[mac_address] = {
                "name": device_info.name if device_info else "Simulated Device",
                "type": device_info.device_type.value if device_info else "unknown",
                "connected_at": datetime.utcnow().isoformat(),
            }
            return {"status": "connected", "mac": mac_address, "simulated": True}

    async def disconnect(self, mac_address: str) -> Dict[str, Any]:
        """Desconecta um dispositivo Bluetooth."""
        if mac_address not in self._connected:
            return {"status": "not_connected"}

        info = self._connected.pop(mac_address)
        client = info.get("client")
        if client and BLEAK_AVAILABLE:
            try:
                await client.disconnect()
            except Exception:
                pass

        return {"status": "disconnected", "mac": mac_address}

    async def disconnect_all(self):
        """Desconecta todos os dispositivos."""
        for mac in list(self._connected.keys()):
            await self.disconnect(mac)

    async def set_audio_output(self, mac_address: str) -> Dict[str, Any]:
        """Define dispositivo Bluetooth como saída de áudio."""
        if mac_address not in self._connected:
            conn = await self.connect(mac_address)
            if conn.get("status") not in ["connected", "already_connected"]:
                return conn

        info = self._connected.get(mac_address, {})
        dtype = info.get("type", "unknown")

        # Comando de sistema para redirecionar áudio (Linux/Raspberry Pi)
        import subprocess
        try:
            # PulseAudio
            result = subprocess.run(
                ["pactl", "set-default-sink", f"bluez_sink.{mac_address.replace(':', '_')}.a2dp_sink"],
                capture_output=True, text=True, timeout=5
            )
            success = result.returncode == 0
        except Exception:
            success = False

        return {
            "status": "audio_routed" if success else "audio_route_failed",
            "mac": mac_address,
            "device_type": dtype,
            "note": "Use pactl manualmente se necessário"
        }

    async def pair(self, mac_address: str) -> Dict[str, Any]:
        """Realiza pareamento com dispositivo."""
        import subprocess
        try:
            result = subprocess.run(
                ["bluetoothctl", "--", "pair", mac_address],
                capture_output=True, text=True, timeout=30
            )
            if "successful" in result.stdout.lower():
                await self.trust(mac_address)
                return {"status": "paired", "mac": mac_address}
            return {"status": "pair_failed", "output": result.stdout}
        except FileNotFoundError:
            # bluetoothctl não disponível (desktop/dev)
            if mac_address not in self._trusted:
                self._trusted.append(mac_address)
            await self._save_device_trusted(mac_address)
            return {"status": "paired_simulated", "mac": mac_address}

    async def trust(self, mac_address: str) -> Dict[str, Any]:
        """Marca dispositivo como confiável."""
        if mac_address not in self._trusted:
            self._trusted.append(mac_address)
        await self._save_device_trusted(mac_address)
        return {"status": "trusted", "mac": mac_address}

    async def get_connected_devices(self) -> List[Dict[str, Any]]:
        """Retorna dispositivos conectados."""
        return [{"mac": mac, **info} for mac, info in self._connected.items()]

    async def get_paired_devices(self) -> List[Dict[str, Any]]:
        """Retorna dispositivos pareados (do banco)."""
        db = await get_db()
        cur = await db.execute("SELECT * FROM bluetooth_devices ORDER BY last_conn DESC NULLS LAST")
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_connected"] = d["mac_address"] in self._connected
            result.append(d)
        return result

    # ─── Voice Call via BT ───────────────────────────────────────────────────

    async def route_call_to_bluetooth(self, mac_address: str) -> Dict[str, Any]:
        """Roteia chamada telefônica para dispositivo BT (fone/caixa)."""
        if mac_address not in self._connected:
            await self.connect(mac_address)
        self._active_call_device = mac_address
        return {"status": "call_routed", "device": mac_address}

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _classify_device(self, name: str) -> BluetoothDeviceType:
        name_lower = name.lower()
        for key, dtype in DEVICE_CLASSIFIERS.items():
            if key in name_lower:
                return dtype
        return BluetoothDeviceType.unknown

    def _mock_scan(self) -> List[BluetoothDevice]:
        return [
            BluetoothDevice(mac_address="AA:BB:CC:11:22:33", name="JBL Flip 6",
                           device_type=BluetoothDeviceType.speaker, trusted=False, rssi=-65),
            BluetoothDevice(mac_address="DD:EE:FF:44:55:66", name="Sony WH-1000XM5",
                           device_type=BluetoothDeviceType.headphone, trusted=True, rssi=-45),
            BluetoothDevice(mac_address="11:22:33:AA:BB:CC", name="Pioneer CarAudio",
                           device_type=BluetoothDeviceType.car_audio, trusted=False, rssi=-70),
            BluetoothDevice(mac_address="77:88:99:DD:EE:FF", name="Samsung TV",
                           device_type=BluetoothDeviceType.tv, trusted=False, rssi=-80),
        ]

    async def _save_device(self, dev: BluetoothDevice):
        try:
            db = await get_db()
            await db.execute(
                "INSERT OR REPLACE INTO bluetooth_devices VALUES (?,?,?,?,?,?,?)",
                (dev.mac_address, dev.name, dev.device_type.value,
                 1 if dev.trusted else 0,
                 datetime.utcnow().isoformat(), None, json.dumps(dev.meta))
            )
            await db.commit()
        except Exception as e:
            logger.debug(f"BT save device error: {e}")

    async def _save_device_trusted(self, mac_address: str):
        try:
            db = await get_db()
            await db.execute(
                "UPDATE bluetooth_devices SET trusted=1 WHERE mac_address=?",
                (mac_address,)
            )
            await db.commit()
        except Exception as e:
            logger.debug(f"BT trust save error: {e}")

    async def _update_last_conn(self, mac_address: str):
        try:
            db = await get_db()
            await db.execute(
                "UPDATE bluetooth_devices SET last_conn=? WHERE mac_address=?",
                (datetime.utcnow().isoformat(), mac_address)
            )
            await db.commit()
        except Exception as e:
            logger.debug(f"BT last_conn error: {e}")

    @property
    def connected_count(self) -> int:
        return len(self._connected)


bluetooth_service = BluetoothService()
