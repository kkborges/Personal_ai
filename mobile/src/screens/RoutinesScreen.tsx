/**
 * RoutinesScreen.tsx — Gerenciamento de rotinas agendadas
 */
import React, { useState, useEffect } from "react";
import { View, Text, FlatList, TouchableOpacity, Switch, StyleSheet, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#4caf50",
            text:"#e8e8e8", muted:"#888", error:"#ff4444", success:"#44ff88" };

export default function RoutinesScreen() {
  const [routines, setRoutines] = useState<any[]>([]);
  const [loading, setLoading]   = useState(false);

  useEffect(() => { loadRoutines(); }, []);

  const loadRoutines = async () => {
    setLoading(true);
    const res = await personalAI.getRoutines();
    if (res.data?.routines) setRoutines(res.data.routines);
    setLoading(false);
  };

  const toggle = async (id: string, enabled: boolean) => {
    await personalAI.toggleRoutine(id, !enabled);
    loadRoutines();
  };

  const cronLabel = (expr: string) => {
    const presets: Record<string,string> = {
      "*/1 * * * *": "A cada minuto",
      "*/30 * * * *": "A cada 30min",
      "0 7 * * *": "Diário às 7h",
      "0 7 * * 1-5": "Dias úteis às 7h",
      "0 21 * * *": "Diário às 21h",
      "0 9 * * 1": "Segunda às 9h",
    };
    return presets[expr] || expr;
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Rotinas</Text>
        <TouchableOpacity onPress={loadRoutines}>
          <Ionicons name="refresh" size={22} color={C.primary} />
        </TouchableOpacity>
      </View>

      <FlatList
        data={routines}
        keyExtractor={(r) => r.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <View style={styles.cardMain}>
              <View style={[styles.dot, { backgroundColor: item.enabled ? C.success : C.muted }]} />
              <View style={styles.info}>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.cron}>{cronLabel(item.cron_expr)}</Text>
                {item.description && <Text style={styles.desc}>{item.description}</Text>}
                <View style={styles.statsRow}>
                  <Text style={styles.stat}>
                    {item.run_count ?? 0}× executada
                  </Text>
                  {item.last_run && (
                    <Text style={styles.stat}>
                      Última: {new Date(item.last_run).toLocaleDateString("pt-BR")}
                    </Text>
                  )}
                </View>
              </View>
              <Switch
                value={item.enabled}
                onValueChange={() => toggle(item.id, item.enabled)}
                trackColor={{ false:"#333", true:C.primary+"66" }}
                thumbColor={item.enabled ? C.primary : "#666"}
              />
            </View>
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="repeat-outline" size={48} color={C.muted} />
            <Text style={styles.emptyText}>Nenhuma rotina configurada</Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:{ flex:1, backgroundColor:C.bg },
  header:   { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
              paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:    { color:C.text, fontSize:20, fontWeight:"bold" },
  list:     { paddingHorizontal:16, paddingTop:12, paddingBottom:24 },
  card:     { backgroundColor:C.card, borderRadius:14, padding:14, marginBottom:8 },
  cardMain: { flexDirection:"row", alignItems:"flex-start", gap:10 },
  dot:      { width:10, height:10, borderRadius:5, marginTop:5 },
  info:     { flex:1 },
  name:     { color:C.text, fontSize:14, fontWeight:"600" },
  cron:     { color:C.primary, fontSize:12, marginTop:2 },
  desc:     { color:C.muted, fontSize:12, marginTop:2 },
  statsRow: { flexDirection:"row", gap:12, marginTop:6 },
  stat:     { color:C.muted, fontSize:11 },
  empty:    { alignItems:"center", paddingTop:60, gap:10 },
  emptyText:{ color:C.muted, fontSize:14 },
});
