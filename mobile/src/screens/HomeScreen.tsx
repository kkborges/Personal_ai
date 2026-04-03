/**
 * HomeScreen.tsx — Dashboard principal do app
 */
import React, { useEffect, useState } from "react";
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useAppStore } from "../store/appStore";
import { personalAI, syncOfflineQueue } from "../services/api";

const C = {
  bg: "#0f0f0f", card: "#1a1a2e", primary: "#6c63ff",
  text: "#e8e8e8", muted: "#888", success: "#44ff88",
  error: "#ff4444", warning: "#ff9800", accent: "#00d4ff",
};

interface Stat { label: string; value: string; icon: string; color: string }

export default function HomeScreen({ navigation }: any) {
  const { status, isConnected, pendingOfflineMessages } = useAppStore();
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState<Stat[]>([]);
  const [greeting, setGreeting] = useState("");

  useEffect(() => {
    const h = new Date().getHours();
    if (h < 12)      setGreeting("Bom dia! ☀️");
    else if (h < 18) setGreeting("Boa tarde! 🌤");
    else             setGreeting("Boa noite! 🌙");
    loadData();
  }, []);

  const loadData = async () => {
    const [statusRes, metricsRes] = await Promise.all([
      personalAI.status(),
      personalAI.getMetrics(),
    ]);
    const s = statusRes.data || {};
    const m = metricsRes.data || {};
    setStats([
      { label: "Saúde do Sistema", value: `${s.health_score ?? 100}%`,  icon: "heart",          color: C.success },
      { label: "CPU",              value: `${Math.round(m.cpu_percent ?? 0)}%`,   icon: "speedometer",    color: C.accent },
      { label: "Memória",          value: `${Math.round(m.memory_percent ?? 0)}%`, icon: "memory",         color: C.warning },
      { label: "Pendentes Sync",   value: `${s.pending_sync ?? 0}`,     icon: "sync",           color: pendingOfflineMessages > 0 ? C.warning : C.success },
    ]);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadData(), syncOfflineQueue()]);
    setRefreshing(false);
  };

  const menuItems = [
    { label: "Chat",        icon: "chatbubbles-outline",  screen: "Chat",       color: C.primary },
    { label: "Memória",     icon: "brain-outline",        screen: "Memory",     color: "#9c27b0" },
    { label: "Calendário",  icon: "calendar-outline",     screen: "Calendar",   color: "#2196f3" },
    { label: "Rotinas",     icon: "repeat-outline",       screen: "Routines",   color: "#4caf50" },
    { label: "Bluetooth",   icon: "bluetooth-outline",    screen: "Bluetooth",  color: "#00bcd4" },
    { label: "Apps",        icon: "apps-outline",         screen: "Apps",       color: "#ff5722" },
    { label: "Monitor",     icon: "pulse-outline",        screen: "Monitor",    color: "#795548" },
    { label: "Ajustes",     icon: "settings-outline",     screen: "Settings",   color: "#607d8b" },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
        showsVerticalScrollIndicator={false}>

        {/* ── Header ── */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>{greeting}</Text>
            <Text style={styles.subtitle}>Personal AI v{status.version}</Text>
          </View>
          <View style={[styles.onlineBadge, isConnected ? styles.onlineGreen : styles.onlineRed]}>
            <Ionicons name={isConnected ? "wifi" : "wifi-outline"} size={14} color="#fff" />
            <Text style={styles.onlineText}>{isConnected ? "Online" : "Offline"}</Text>
          </View>
        </View>

        {/* ── Offline warning ── */}
        {!isConnected && (
          <View style={styles.offlineBanner}>
            <Ionicons name="cloud-offline-outline" size={16} color={C.warning} />
            <Text style={styles.offlineText}>
              Modo offline · {pendingOfflineMessages} mensagem(s) aguardando sincronização
            </Text>
          </View>
        )}

        {/* ── Estatísticas ── */}
        <View style={styles.statsGrid}>
          {stats.map((s) => (
            <View key={s.label} style={styles.statCard}>
              <Ionicons name={s.icon as any} size={22} color={s.color} />
              <Text style={[styles.statValue, { color: s.color }]}>{s.value}</Text>
              <Text style={styles.statLabel}>{s.label}</Text>
            </View>
          ))}
        </View>

        {/* ── Atalho rápido para chat ── */}
        <TouchableOpacity
          style={styles.chatShortcut}
          onPress={() => navigation.navigate("Chat")}>
          <View style={styles.chatShortcutIcon}>
            <Ionicons name="mic" size={28} color="#fff" />
          </View>
          <View>
            <Text style={styles.chatShortcutTitle}>Iniciar Conversa</Text>
            <Text style={styles.chatShortcutSub}>Toque para falar ou digitar</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={C.muted} />
        </TouchableOpacity>

        {/* ── Menu principal ── */}
        <Text style={styles.sectionTitle}>Funcionalidades</Text>
        <View style={styles.menuGrid}>
          {menuItems.map((item) => (
            <TouchableOpacity
              key={item.label}
              style={styles.menuItem}
              onPress={() => navigation.navigate(item.screen)}>
              <View style={[styles.menuIcon, { backgroundColor: item.color + "22" }]}>
                <Ionicons name={item.icon as any} size={26} color={item.color} />
              </View>
              <Text style={styles.menuLabel}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:     { flex: 1, backgroundColor: C.bg },
  scroll:        { paddingHorizontal: 16, paddingBottom: 24 },
  header:        { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                   paddingVertical: 20 },
  greeting:      { color: C.text, fontSize: 24, fontWeight: "bold" },
  subtitle:      { color: C.muted, fontSize: 13, marginTop: 2 },
  onlineBadge:   { flexDirection:"row", alignItems:"center", paddingHorizontal:10,
                   paddingVertical:5, borderRadius:12 },
  onlineGreen:   { backgroundColor: "#1b5e20" },
  onlineRed:     { backgroundColor: "#b71c1c" },
  onlineText:    { color:"#fff", fontSize:12, marginLeft:4, fontWeight:"600" },
  offlineBanner: { backgroundColor:"#2d1b00", borderRadius:10, padding:12, marginBottom:16,
                   flexDirection:"row", alignItems:"center" },
  offlineText:   { color:C.warning, marginLeft:8, fontSize:13, flex:1 },
  statsGrid:     { flexDirection:"row", flexWrap:"wrap", marginBottom:16, gap:8 },
  statCard:      { flex:1, minWidth:"45%", backgroundColor:C.card, borderRadius:14,
                   padding:14, alignItems:"center" },
  statValue:     { fontSize:22, fontWeight:"bold", marginTop:8 },
  statLabel:     { color:C.muted, fontSize:11, marginTop:2, textAlign:"center" },
  chatShortcut:  { backgroundColor:C.card, borderRadius:16, padding:16, marginBottom:20,
                   flexDirection:"row", alignItems:"center", gap:14 },
  chatShortcutIcon: { width:52, height:52, borderRadius:26, backgroundColor:C.primary,
                      alignItems:"center", justifyContent:"center" },
  chatShortcutTitle: { color:C.text, fontSize:16, fontWeight:"600" },
  chatShortcutSub:   { color:C.muted, fontSize:12, marginTop:2 },
  sectionTitle:  { color:C.text, fontSize:16, fontWeight:"600", marginBottom:12 },
  menuGrid:      { flexDirection:"row", flexWrap:"wrap", gap:10 },
  menuItem:      { width:"22%", aspectRatio:1, backgroundColor:C.card, borderRadius:16,
                   alignItems:"center", justifyContent:"center" },
  menuIcon:      { width:48, height:48, borderRadius:14, alignItems:"center",
                   justifyContent:"center", marginBottom:6 },
  menuLabel:     { color:C.text, fontSize:11, textAlign:"center" },
});
