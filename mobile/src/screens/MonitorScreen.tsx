/**
 * MonitorScreen.tsx — Monitor do sistema + auto-melhorias
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, RefreshControl, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#6c63ff",
            text:"#e8e8e8", muted:"#888", success:"#44ff88",
            error:"#ff4444", warning:"#ff9800" };

const Gauge = ({ label, value, max = 100, color }: any) => {
  const pct = Math.round((value / max) * 100);
  const barColor = pct > 80 ? C.error : pct > 60 ? C.warning : C.success;
  return (
    <View style={gaugeStyles.container}>
      <View style={gaugeStyles.header}>
        <Text style={gaugeStyles.label}>{label}</Text>
        <Text style={[gaugeStyles.value, { color: barColor }]}>{pct}%</Text>
      </View>
      <View style={gaugeStyles.track}>
        <View style={[gaugeStyles.fill, { width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }]} />
      </View>
    </View>
  );
};
const gaugeStyles = StyleSheet.create({
  container:{ marginBottom:10 },
  header:   { flexDirection:"row", justifyContent:"space-between" },
  label:    { color:C.muted, fontSize:12 },
  value:    { fontSize:13, fontWeight:"bold" },
  track:    { height:6, backgroundColor:"#222", borderRadius:3, marginTop:4 },
  fill:     { height:6, borderRadius:3 },
});

export default function MonitorScreen() {
  const [metrics, setMetrics]   = useState<any>(null);
  const [patches, setPatches]   = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    const [mRes, pRes] = await Promise.all([
      personalAI.getMetrics(),
      personalAI.getPatches(),
    ]);
    if (mRes.data) setMetrics(mRes.data);
    if (pRes.data?.patches) setPatches(pRes.data.patches || []);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const applyPatch = (id: string, title: string) => {
    Alert.alert(
      "Aplicar melhoria",
      `Deseja aplicar "${title}"?\nO sistema irá aplicar e testar automaticamente.`,
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Aplicar",
          onPress: async () => {
            const res = await personalAI.applyPatch(id);
            Alert.alert(res.data?.success ? "✅ Aplicado" : "❌ Erro",
                        res.data?.message || res.error || "");
            loadData();
          },
        },
      ]
    );
  };

  const healthColor = (score: number) =>
    score >= 90 ? C.success : score >= 70 ? C.warning : C.error;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Monitor do Sistema</Text>
        <TouchableOpacity onPress={loadData}>
          <Ionicons name="refresh" size={22} color={C.primary} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
        showsVerticalScrollIndicator={false}>

        {metrics && (
          <>
            {/* ── Saúde geral ── */}
            <View style={styles.healthCard}>
              <Text style={styles.sectionTitle}>🏥 Saúde do Sistema</Text>
              <Text style={[styles.healthScore, { color: healthColor(metrics.health_score ?? 100) }]}>
                {metrics.health_score ?? 100}
              </Text>
              <Text style={styles.healthLabel}>/100</Text>
            </View>

            {/* ── Gráficos ── */}
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>📊 Recursos</Text>
              <Gauge label="CPU"    value={metrics.cpu_percent    ?? 0} />
              <Gauge label="Memória" value={metrics.memory_percent ?? 0} />
              {metrics.disk_used_percent !== undefined &&
                <Gauge label="Disco" value={metrics.disk_used_percent} />}
            </View>

            {/* ── Detalhes ── */}
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>ℹ️ Detalhes</Text>
              {[
                ["Uptime",    `${Math.round((metrics.uptime_seconds ?? 0) / 3600)}h`],
                ["Memória",   `${Math.round(metrics.memory_mb ?? 0)} MB`],
                ["Disco livre", `${((metrics.disk_free_gb ?? 0)).toFixed(1)} GB`],
                ["Threads",   metrics.threads ?? "-"],
                ["Mensagens", metrics.db_rows?.messages ?? 0],
                ["Memórias",  metrics.db_rows?.memories ?? 0],
              ].map(([k, v]) => (
                <View key={k as string} style={styles.detailRow}>
                  <Text style={styles.detailKey}>{k}</Text>
                  <Text style={styles.detailVal}>{v}</Text>
                </View>
              ))}
            </View>
          </>
        )}

        {/* ── Melhorias propostas ── */}
        {patches.length > 0 && (
          <>
            <Text style={styles.sectionTitleOuter}>🔧 Melhorias Propostas ({patches.length})</Text>
            {patches.filter((p) => p.status === "proposed").map((p) => (
              <View key={p.id} style={styles.patchCard}>
                <View style={styles.patchHeader}>
                  <Text style={styles.patchTitle}>{p.title}</Text>
                  <View style={[styles.patchBadge,
                    { backgroundColor: p.patch_type === "fix" ? C.error + "33" : C.primary + "33" }]}>
                    <Text style={[styles.patchType,
                      { color: p.patch_type === "fix" ? C.error : C.primary }]}>
                      {p.patch_type}
                    </Text>
                  </View>
                </View>
                {p.description && <Text style={styles.patchDesc}>{p.description}</Text>}
                <TouchableOpacity
                  style={styles.applyBtn}
                  onPress={() => applyPatch(p.id, p.title)}>
                  <Ionicons name="checkmark-circle-outline" size={16} color={C.success} />
                  <Text style={styles.applyText}>Aplicar</Text>
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:        { flex:1, backgroundColor:C.bg },
  header:           { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                      paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:            { color:C.text, fontSize:20, fontWeight:"bold" },
  scroll:           { paddingHorizontal:16, paddingTop:12 },
  healthCard:       { backgroundColor:C.card, borderRadius:14, padding:20, marginBottom:12,
                      alignItems:"center" },
  healthScore:      { fontSize:64, fontWeight:"bold" },
  healthLabel:      { color:C.muted, fontSize:18 },
  card:             { backgroundColor:C.card, borderRadius:14, padding:14, marginBottom:12 },
  sectionTitle:     { color:C.text, fontSize:14, fontWeight:"600", marginBottom:12 },
  sectionTitleOuter:{ color:C.text, fontSize:15, fontWeight:"600", marginBottom:8 },
  detailRow:        { flexDirection:"row", justifyContent:"space-between",
                      paddingVertical:6, borderTopWidth:1, borderTopColor:"#222" },
  detailKey:        { color:C.muted, fontSize:13 },
  detailVal:        { color:C.text, fontSize:13, fontWeight:"600" },
  patchCard:        { backgroundColor:C.card, borderRadius:14, padding:14, marginBottom:8 },
  patchHeader:      { flexDirection:"row", justifyContent:"space-between", alignItems:"center", marginBottom:6 },
  patchTitle:       { color:C.text, fontSize:14, fontWeight:"600", flex:1, marginRight:8 },
  patchBadge:       { paddingHorizontal:8, paddingVertical:3, borderRadius:6 },
  patchType:        { fontSize:11, fontWeight:"600" },
  patchDesc:        { color:C.muted, fontSize:12, marginBottom:8 },
  applyBtn:         { flexDirection:"row", alignItems:"center", gap:6, alignSelf:"flex-start",
                      backgroundColor:"#1a3a1a", paddingHorizontal:12, paddingVertical:6, borderRadius:8 },
  applyText:        { color:C.success, fontSize:13, fontWeight:"600" },
});
