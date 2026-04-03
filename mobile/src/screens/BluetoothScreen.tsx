/**
 * BluetoothScreen.tsx — Gerenciamento de dispositivos Bluetooth
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, TouchableOpacity, FlatList,
  StyleSheet, ActivityIndicator, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#00bcd4", text:"#e8e8e8",
            muted:"#888", success:"#44ff88", error:"#ff4444" };

const DEVICE_ICONS: Record<string, string> = {
  speaker:"volume-high", headphone:"headset", tv:"tv", car:"car",
  phone:"phone-portrait", keyboard:"keyboard", unknown:"bluetooth",
};

export default function BluetoothScreen() {
  const [devices, setDevices]   = useState<any[]>([]);
  const [trusted, setTrusted]   = useState<any[]>([]);
  const [scanning, setScanning] = useState(false);

  useEffect(() => { loadTrusted(); }, []);

  const loadTrusted = async () => {
    const res = await personalAI.getTrustedDevices();
    if (res.data) setTrusted(res.data.devices || []);
  };

  const scan = async () => {
    setScanning(true);
    setDevices([]);
    const res = await personalAI.scanBluetooth(10);
    setScanning(false);
    if (res.data?.devices) setDevices(res.data.devices);
    else Alert.alert("Bluetooth", res.error || "Nenhum dispositivo encontrado");
  };

  const connect = async (mac: string, name: string) => {
    Alert.alert("Conectar", `Conectar ao dispositivo "${name}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Conectar", onPress: async () => {
          const res = await personalAI.connectBluetooth(mac);
          Alert.alert(res.data?.success ? "✅ Conectado" : "❌ Erro", res.data?.message || res.error || "");
          loadTrusted();
        },
      },
    ]);
  };

  const renderDevice = ({ item }: { item: any }) => {
    const iconName = DEVICE_ICONS[item.device_type] || "bluetooth";
    const isTrusted = trusted.some((t) => t.mac_address === item.address);
    return (
      <TouchableOpacity style={styles.deviceCard} onPress={() => connect(item.address, item.name)}>
        <View style={[styles.deviceIcon, { backgroundColor: isTrusted ? C.primary + "33" : "#222" }]}>
          <Ionicons name={iconName as any} size={24} color={isTrusted ? C.primary : C.muted} />
        </View>
        <View style={styles.deviceInfo}>
          <Text style={styles.deviceName}>{item.name || "Dispositivo desconhecido"}</Text>
          <Text style={styles.deviceMac}>{item.address}</Text>
          {item.rssi && <Text style={styles.deviceRssi}>Sinal: {item.rssi} dBm</Text>}
        </View>
        {isTrusted && (
          <View style={styles.trustedBadge}>
            <Ionicons name="checkmark-circle" size={18} color={C.success} />
          </View>
        )}
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Bluetooth</Text>
        <TouchableOpacity style={[styles.scanBtn, scanning && styles.scanBtnActive]} onPress={scan} disabled={scanning}>
          {scanning
            ? <ActivityIndicator size="small" color="#fff" />
            : <Ionicons name="search" size={20} color="#fff" />}
          <Text style={styles.scanText}>{scanning ? "Escaneando..." : "Escanear"}</Text>
        </TouchableOpacity>
      </View>

      {trusted.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Dispositivos Confiáveis</Text>
          {trusted.map((d) => renderDevice({ item: { ...d, address: d.mac_address } }))}
        </>
      )}

      {devices.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Dispositivos Encontrados ({devices.length})</Text>
          <FlatList
            data={devices}
            keyExtractor={(d) => d.address}
            renderItem={renderDevice}
            showsVerticalScrollIndicator={false}
          />
        </>
      )}

      {!scanning && devices.length === 0 && trusted.length === 0 && (
        <View style={styles.empty}>
          <Ionicons name="bluetooth-outline" size={64} color={C.muted} />
          <Text style={styles.emptyText}>Nenhum dispositivo</Text>
          <Text style={styles.emptyHint}>Toque em "Escanear" para buscar dispositivos</Text>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:      { flex:1, backgroundColor:C.bg },
  header:         { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                    paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:          { color:C.text, fontSize:20, fontWeight:"bold" },
  scanBtn:        { flexDirection:"row", alignItems:"center", backgroundColor:C.primary,
                    paddingHorizontal:14, paddingVertical:8, borderRadius:20, gap:6 },
  scanBtnActive:  { backgroundColor:C.primary + "88" },
  scanText:       { color:"#fff", fontSize:13, fontWeight:"600" },
  sectionTitle:   { color:C.muted, fontSize:12, fontWeight:"600", marginHorizontal:16,
                    marginTop:16, marginBottom:8, textTransform:"uppercase" },
  deviceCard:     { flexDirection:"row", alignItems:"center", backgroundColor:C.card,
                    marginHorizontal:16, marginVertical:4, borderRadius:12, padding:12, gap:12 },
  deviceIcon:     { width:44, height:44, borderRadius:12, alignItems:"center", justifyContent:"center" },
  deviceInfo:     { flex:1 },
  deviceName:     { color:C.text, fontSize:14, fontWeight:"600" },
  deviceMac:      { color:C.muted, fontSize:11, marginTop:2 },
  deviceRssi:     { color:C.muted, fontSize:11 },
  trustedBadge:   { padding:4 },
  empty:          { flex:1, alignItems:"center", justifyContent:"center" },
  emptyText:      { color:C.text, fontSize:16, fontWeight:"600", marginTop:16 },
  emptyHint:      { color:C.muted, fontSize:13, marginTop:6 },
});
