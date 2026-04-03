"""
services/self_monitoring.py — Auto-monitoramento e auto-melhoria com geração de código
Inclui: métricas de performance, detecção de anomalias, sugestão e geração de código,
testes automáticos e deploy opcional.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)

SELF_IMPROVEMENT_DIR = Path(__file__).parent.parent / "self_improvement"
PATCHES_DIR = SELF_IMPROVEMENT_DIR / "patches"
GENERATED_DIR = SELF_IMPROVEMENT_DIR / "generated"
TESTS_DIR = SELF_IMPROVEMENT_DIR / "tests"


class SelfMonitoringService:
    """Monitora o sistema, detecta problemas e propõe/aplica melhorias com código."""

    def __init__(self):
        self._start_time = time.time()
        self._metrics_buffer: List[Dict] = []
        self._last_improvement_check: Optional[datetime] = None
        self._health_history: List[float] = []
        self._running = False

    async def initialize(self):
        """Inicializa o serviço de monitoramento."""
        self._running = True
        logger.info("✅ SelfMonitoringService inicializado")

    # ─── Coleta de Métricas ───────────────────────────────────────────────────

    async def collect_metrics(self) -> Dict[str, Any]:
        """Coleta métricas do sistema em tempo real."""
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        uptime = time.time() - self._start_time

        # Métricas de banco de dados
        db_metrics = await self._get_db_metrics()

        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_s": uptime,
            "cpu_percent": cpu,
            "memory_mb": mem.used / 1024 / 1024,
            "memory_percent": mem.percent,
            "memory_available_mb": mem.available / 1024 / 1024,
            "disk_free_gb": disk.free / 1024 / 1024 / 1024,
            "disk_percent": disk.percent,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            **db_metrics,
        }

        # Coleta de processo atual
        try:
            proc = psutil.Process(os.getpid())
            metrics["process_memory_mb"] = proc.memory_info().rss / 1024 / 1024
            metrics["process_cpu_percent"] = proc.cpu_percent(interval=None)
            metrics["process_threads"] = proc.num_threads()
            metrics["open_files"] = len(proc.open_files())
        except Exception:
            pass

        self._metrics_buffer.append(metrics)
        if len(self._metrics_buffer) > 1000:
            self._metrics_buffer = self._metrics_buffer[-1000:]

        # Salva no banco
        await self._save_metrics(metrics)

        return metrics

    async def _get_db_metrics(self) -> Dict[str, Any]:
        try:
            db = await get_db()
            tables_info = {}
            for table in ["messages", "memories", "jobs", "monitoring_metrics", "sync_queue"]:
                try:
                    cur = await db.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                    row = await cur.fetchone()
                    tables_info[f"table_{table}_rows"] = row["cnt"] if row else 0
                except Exception:
                    tables_info[f"table_{table}_rows"] = -1

            # Jobs pendentes
            cur = await db.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status='pending'")
            row = await cur.fetchone()
            tables_info["pending_jobs"] = row["cnt"] if row else 0

            # Sync pendente
            cur = await db.execute("SELECT COUNT(*) as cnt FROM sync_queue WHERE synced=0")
            row = await cur.fetchone()
            tables_info["pending_sync"] = row["cnt"] if row else 0

            return tables_info
        except Exception:
            return {}

    async def _save_metrics(self, metrics: Dict):
        try:
            db = await get_db()
            key_metrics = ["cpu_percent", "memory_percent", "memory_mb", "disk_percent",
                           "process_memory_mb", "pending_jobs", "pending_sync"]
            for key in key_metrics:
                if key in metrics:
                    await db.execute(
                        "INSERT INTO monitoring_metrics VALUES (?,?,?,?,?,?)",
                        (str(uuid.uuid4()), key, float(metrics[key]), "%", "{}", metrics["timestamp"])
                    )
            await db.commit()
        except Exception as e:
            logger.debug(f"Metrics save error: {e}")

    # ─── Health Score ─────────────────────────────────────────────────────────

    async def calculate_health_score(self, metrics: Dict = None) -> float:
        """Calcula score de saúde do sistema (0-100)."""
        if metrics is None:
            metrics = await self.collect_metrics()

        score = 100.0
        deductions = []

        # CPU
        cpu = metrics.get("cpu_percent", 0)
        if cpu > 90:
            score -= 30
            deductions.append(f"CPU crítico: {cpu:.1f}%")
        elif cpu > 70:
            score -= 15
            deductions.append(f"CPU alto: {cpu:.1f}%")

        # Memória
        mem = metrics.get("memory_percent", 0)
        if mem > 90:
            score -= 25
            deductions.append(f"Memória crítica: {mem:.1f}%")
        elif mem > 75:
            score -= 10
            deductions.append(f"Memória alta: {mem:.1f}%")

        # Disco
        disk = metrics.get("disk_percent", 0)
        if disk > 95:
            score -= 20
            deductions.append(f"Disco crítico: {disk:.1f}%")
        elif disk > 85:
            score -= 8
            deductions.append(f"Disco alto: {disk:.1f}%")

        # Jobs pendentes
        pending = metrics.get("pending_jobs", 0)
        if pending > 100:
            score -= 15
            deductions.append(f"Muitos jobs pendentes: {pending}")
        elif pending > 50:
            score -= 5

        self._health_history.append(score)
        if len(self._health_history) > 100:
            self._health_history = self._health_history[-100:]

        return max(0.0, min(100.0, score))

    # ─── Anomaly Detection ────────────────────────────────────────────────────

    async def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detecta anomalias baseado no histórico de métricas."""
        anomalies = []

        try:
            db = await get_db()

            # CPU persistentemente alto
            cur = await db.execute(
                "SELECT AVG(value) as avg_val FROM monitoring_metrics "
                "WHERE metric_name='cpu_percent' AND recorded_at > datetime('now','-1 hour')"
            )
            row = await cur.fetchone()
            if row and row["avg_val"] and row["avg_val"] > 80:
                anomalies.append({
                    "type": "high_cpu", "severity": "warning",
                    "message": f"CPU média {row['avg_val']:.1f}% na última hora",
                    "value": row["avg_val"]
                })

            # Memória crescente
            cur = await db.execute(
                "SELECT value, recorded_at FROM monitoring_metrics "
                "WHERE metric_name='memory_mb' ORDER BY recorded_at DESC LIMIT 10"
            )
            rows = await cur.fetchall()
            if len(rows) >= 5:
                values = [r["value"] for r in rows]
                if values[0] > values[-1] * 1.3:  # 30% de crescimento
                    anomalies.append({
                        "type": "memory_leak", "severity": "critical",
                        "message": f"Possível memory leak: {values[-1]:.0f}MB → {values[0]:.0f}MB",
                        "value": values[0]
                    })

            # Jobs falhando muito
            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status='failed' "
                "AND created_at > datetime('now','-1 hour')"
            )
            row = await cur.fetchone()
            if row and row["cnt"] > 10:
                anomalies.append({
                    "type": "job_failures", "severity": "warning",
                    "message": f"{row['cnt']} jobs falharam na última hora",
                    "value": row["cnt"]
                })

        except Exception as e:
            logger.debug(f"Anomaly detection error: {e}")

        return anomalies

    # ─── Self-Improvement ─────────────────────────────────────────────────────

    async def generate_improvement(self, context: Dict = None) -> Dict:
        """Gera melhorias de código usando IA baseado nas métricas."""
        metrics = await self.collect_metrics()
        anomalies = await self.detect_anomalies()
        health = await self.calculate_health_score(metrics)

        # Determina o que melhorar
        improvement_prompt = self._build_improvement_prompt(metrics, anomalies, health, context)

        try:
            from services.provider_router import provider_router
            result = await provider_router.complete(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": improvement_prompt}
                ],
                max_tokens=4096,
                task_type="self_improvement"
            )

            patch_id = str(uuid.uuid4())
            patch_type = "optimization" if health < 70 else "feature"

            # Parse do código gerado
            generated = result["content"]
            code_blocks = self._extract_code_blocks(generated)
            test_blocks = self._extract_test_blocks(generated)

            # Salva o patch
            patch_file = GENERATED_DIR / f"patch_{patch_id[:8]}.py"
            test_file = TESTS_DIR / f"test_{patch_id[:8]}.py"

            if code_blocks:
                patch_file.write_text(code_blocks[0], encoding="utf-8")
            if test_blocks:
                test_file.write_text(test_blocks[0], encoding="utf-8")

            # Registra no banco
            db = await get_db()
            await db.execute(
                "INSERT INTO improvement_patches VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (
                    patch_id,
                    f"Melhoria automática #{patch_id[:8]}",
                    generated[:500],
                    patch_type,
                    "proposed",
                    str(patch_file) if code_blocks else None,
                    code_blocks[0] if code_blocks else generated,
                    test_blocks[0] if test_blocks else None,
                    result.get("provider", "unknown"),
                    datetime.utcnow().isoformat(),
                )
            )
            await db.commit()

            return {
                "patch_id": patch_id,
                "health_score": health,
                "anomalies_found": len(anomalies),
                "patch_type": patch_type,
                "description": generated[:300] + "..." if len(generated) > 300 else generated,
                "has_code": bool(code_blocks),
                "has_tests": bool(test_blocks),
                "code": code_blocks[0] if code_blocks else None,
                "test_code": test_blocks[0] if test_blocks else None,
                "provider_used": result.get("provider", "unknown"),
                "status": "proposed",
            }

        except Exception as e:
            logger.error(f"Improvement generation error: {e}")
            return {"error": str(e), "health_score": health}

    async def run_tests(self, patch_id: str) -> Dict:
        """Executa os testes gerados para um patch."""
        db = await get_db()
        cur = await db.execute("SELECT * FROM improvement_patches WHERE id=?", (patch_id,))
        row = await cur.fetchone()
        if not row:
            return {"success": False, "error": "Patch não encontrado"}

        test_code = row["test_code"]
        if not test_code:
            return {"success": False, "error": "Sem código de teste"}

        # Cria arquivo de teste temporário
        test_file = TESTS_DIR / f"test_run_{patch_id[:8]}.py"
        test_file.write_text(test_code, encoding="utf-8")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short", "--timeout=30"],
                capture_output=True, text=True, timeout=60,
                cwd=str(Path(__file__).parent.parent)
            )

            success = result.returncode == 0
            test_output = result.stdout + result.stderr

            # Atualiza status
            status = "approved" if success else "rejected"
            await db.execute(
                "UPDATE improvement_patches SET status=?, test_result=? WHERE id=?",
                (status, test_output[:2000], patch_id)
            )
            await db.commit()

            return {
                "success": success,
                "status": status,
                "output": test_output,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout nos testes"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def apply_patch(self, patch_id: str) -> Dict:
        """Aplica um patch aprovado ao código."""
        if not settings.auto_deploy_patches:
            return {"success": False, "error": "Auto-deploy desativado. Configure auto_deploy_patches=true"}

        db = await get_db()
        cur = await db.execute("SELECT * FROM improvement_patches WHERE id=?", (patch_id,))
        row = await cur.fetchone()
        if not row:
            return {"success": False, "error": "Patch não encontrado"}
        if row["status"] not in ["approved"]:
            return {"success": False, "error": f"Patch precisa ser aprovado primeiro. Status: {row['status']}"}

        # Backup do arquivo antes de aplicar
        file_path = row["file_path"]
        if file_path and Path(file_path).exists():
            backup = file_path + ".backup"
            import shutil
            shutil.copy2(file_path, backup)
            logger.info(f"Backup criado: {backup}")

        try:
            # Aplica o patch
            code = row["generated_code"]
            patch_file = PATCHES_DIR / f"applied_{patch_id[:8]}.py"
            patch_file.write_text(code, encoding="utf-8")

            # Atualiza status
            await db.execute(
                "UPDATE improvement_patches SET status='applied', applied_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), patch_id)
            )
            await db.commit()

            return {
                "success": True,
                "patch_id": patch_id,
                "applied_at": datetime.utcnow().isoformat(),
                "file": str(patch_file),
            }

        except Exception as e:
            logger.error(f"Apply patch error: {e}")
            return {"success": False, "error": str(e)}

    # ─── Relatório Completo ───────────────────────────────────────────────────

    async def generate_report(self, period_hours: int = 24) -> Dict:
        """Gera relatório completo de monitoramento com sugestões."""
        metrics = await self.collect_metrics()
        health = await self.calculate_health_score(metrics)
        anomalies = await self.detect_anomalies()

        # Histórico de patches
        db = await get_db()
        cur = await db.execute(
            "SELECT * FROM improvement_patches ORDER BY created_at DESC LIMIT 10"
        )
        patches = [dict(r) for r in await cur.fetchall()]

        # Uso de providers
        cur = await db.execute(
            "SELECT provider, COUNT(*) as calls, SUM(cost_usd) as total_cost, "
            "AVG(latency_ms) as avg_latency FROM provider_usage "
            "WHERE created_at > datetime('now',?) GROUP BY provider",
            (f"-{period_hours} hours",)
        )
        provider_stats = [dict(r) for r in await cur.fetchall()]

        # Atividade de jobs
        cur = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs "
            "WHERE created_at > datetime('now',?) GROUP BY status",
            (f"-{period_hours} hours",)
        )
        job_stats = {r["status"]: r["cnt"] for r in await cur.fetchall()}

        return {
            "period_hours": period_hours,
            "health_score": health,
            "health_trend": self._calculate_trend(),
            "current_metrics": metrics,
            "anomalies": anomalies,
            "provider_stats": provider_stats,
            "job_stats": job_stats,
            "recent_patches": patches[:5],
            "recommendations": self._generate_recommendations(health, anomalies, metrics),
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _generate_recommendations(self, health: float, anomalies: List, metrics: Dict) -> List[str]:
        recs = []
        if health < 50:
            recs.append("🔴 Sistema em estado crítico. Reiniciar serviços recomendado.")
        if metrics.get("cpu_percent", 0) > 70:
            recs.append("⚡ Otimizar queries e processos pesados para reduzir CPU.")
        if metrics.get("memory_percent", 0) > 80:
            recs.append("💾 Limpar cache e monitorar possível memory leak.")
        if metrics.get("disk_percent", 0) > 85:
            recs.append("💿 Limpar logs antigos e dados temporários.")
        if metrics.get("pending_jobs", 0) > 50:
            recs.append("⏱️ Aumentar workers de jobs ou revisar jobs problemáticos.")
        for a in anomalies:
            recs.append(f"⚠️ {a['message']}")
        if not recs:
            recs.append("✅ Sistema saudável. Nenhuma ação necessária.")
        return recs

    def _calculate_trend(self) -> str:
        if len(self._health_history) < 3:
            return "stable"
        recent = self._health_history[-3:]
        if recent[-1] > recent[0] + 5:
            return "improving"
        elif recent[-1] < recent[0] - 5:
            return "degrading"
        return "stable"

    def _build_improvement_prompt(self, metrics: Dict, anomalies: List, health: float, context: Dict = None) -> str:
        anomaly_text = "\n".join([f"- {a['message']}" for a in anomalies]) if anomalies else "Nenhuma anomalia detectada"
        return f"""
Analise o estado do Personal AI Mobile e gere melhorias concretas:

MÉTRICAS ATUAIS:
- CPU: {metrics.get('cpu_percent', 0):.1f}%
- Memória: {metrics.get('memory_percent', 0):.1f}% ({metrics.get('memory_mb', 0):.0f}MB)
- Jobs pendentes: {metrics.get('pending_jobs', 0)}
- Saúde geral: {health:.1f}/100

ANOMALIAS DETECTADAS:
{anomaly_text}

CONTEXTO ADICIONAL: {json.dumps(context or {})}

TAREFA:
1. Identifique o principal gargalo/problema
2. Gere código Python funcional para resolver o problema
3. Inclua código de teste (pytest)
4. Seja específico e entregue código completo, não apenas sugestões

Formato de resposta:
```python
# IMPROVEMENT CODE
[código de melhoria aqui]
```

```python
# TEST CODE
[código de teste aqui]
```

Explique brevemente o que foi melhorado e por quê.
"""

    def _get_system_prompt(self) -> str:
        return """Você é um engenheiro de software sênior especialista em Python, FastAPI e otimização de sistemas.
Você analisa métricas de performance e gera código Python funcional e testável para melhorar o sistema.
Sempre entregue código completo, não fragmentos. Inclua testes pytest funcionais.
Foque em melhorias práticas e mensuráveis."""

    def _extract_code_blocks(self, text: str) -> List[str]:
        import re
        pattern = r'```python\n(.*?)```'
        blocks = re.findall(pattern, text, re.DOTALL)
        return [b for b in blocks if "TEST" not in b.split('\n')[0].upper()]

    def _extract_test_blocks(self, text: str) -> List[str]:
        import re
        pattern = r'```python\n(.*?)```'
        blocks = re.findall(pattern, text, re.DOTALL)
        return [b for b in blocks if "TEST" in b.split('\n')[0].upper() or "test_" in b[:50]]

    async def get_patches(self, status: str = None) -> List[Dict]:
        """Retorna patches gerados."""
        db = await get_db()
        if status:
            cur = await db.execute(
                "SELECT * FROM improvement_patches WHERE status=? ORDER BY created_at DESC",
                (status,)
            )
        else:
            cur = await db.execute("SELECT * FROM improvement_patches ORDER BY created_at DESC")
        return [dict(r) for r in await cur.fetchall()]

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time


self_monitoring = SelfMonitoringService()
