/**
 * SettingsScreen.tsx — Configurações do app (servidor, voz, integrações)
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, TextInput, Switch, TouchableOpacity,
  ScrollView, StyleSheet, Alert, ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useAppStore } from "../store/appStore";
import { personalAI } from "../services/api";

const C = {
  bg:"#0f0f0f", card:"#1a1a2e", primary:"#6c63ff",
  text:"#e8e8e8", muted:"#888", border:"#2a2a4a",
  success:"#44ff88", error:"#ff4444",
};

export default function SettingsScreen() {
  const {
    serverUrl, setServerUrl, theme, setTheme,
    language, setLanguage, wakeWord, setWakeWord,
    alwaysListen, setAlwaysListen,
  } = useAppStore();

  const [urlInput, setUrlInput] = useState(serverUrl);
  const [testing, setTesting]   = useState(false);
  const [testOk, setTestOk]     = useState<boolean | null>(null);
  const [config, setConfig]     = useState<any>(null);

  useEffect(() => { loadConfig(); }, []);

  const loadConfig = async () => {
    const res = await personalAI.getConfig();
    if (res.data) setConfig(res.data);
  };

  const testConnection = async () => {
    setTesting(true);
    setTestOk(null);
    try {
      const res = await fetch(`${urlInput}/health`, { signal: AbortSignal.timeout(5000) });
      setTestOk(res.ok);
      if (res.ok) setServerUrl(urlInput);
    } catch {
      setTestOk(false);
    } finally {
      setTesting(false);
    }
  };

  const Section = ({ title }: { title: string }) => (
    <Text style={styles.sectionTitle}>{title}</Text>
  );

  const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowValue}>{children}</View>
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Configurações</Text>
      </View>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

        {/* ── Conexão ── */}
        <Section title="🔗 Servidor" />
        <View style={styles.card}>
          <Text style={styles.label}>URL do Servidor</Text>
          <View style={styles.urlRow}>
            <TextInput
              style={styles.urlInput}
              value={urlInput}
              onChangeText={setUrlInput}
              placeholder="https://seu-dominio.com"
              placeholderTextColor={C.muted}
              autoCapitalize="none"
              keyboardType="url"
            />
            <TouchableOpacity style={styles.testBtn} onPress={testConnection} disabled={testing}>
              {testing
                ? <ActivityIndicator size="small" color={C.primary} />
                : <Ionicons
                    name={testOk === null ? "wifi-outline" : testOk ? "checkmark-circle" : "close-circle"}
                    size={22}
                    color={testOk === null ? C.primary : testOk ? C.success : C.error}
                  />}
            </TouchableOpacity>
          </View>
          {testOk === true  && <Text style={styles.testSuccess}>✅ Conectado com sucesso</Text>}
          {testOk === false && <Text style={styles.testError}>❌ Falha na conexão</Text>}
        </View>

        {/* ── Aparência ── */}
        <Section title="🎨 Aparência" />
        <View style={styles.card}>
          <Row label="Tema">
            {(["dark","light","auto"] as const).map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.themeBtn, theme === t && styles.themeBtnActive]}
                onPress={() => setTheme(t)}>
                <Text style={[styles.themeBtnText, theme === t && styles.themeBtnTextActive]}>
                  {t === "dark" ? "🌙" : t === "light" ? "☀️" : "🔄"}
                </Text>
              </TouchableOpacity>
            ))}
          </Row>
          <Row label="Idioma">
            {(["pt-BR","en-US","es-ES"] as const).map((l) => (
              <TouchableOpacity
                key={l}
                style={[styles.langBtn, language === l && styles.langBtnActive]}
                onPress={() => setLanguage(l)}>
                <Text style={[styles.langText, language === l && { color: C.primary }]}>{l}</Text>
              </TouchableOpacity>
            ))}
          </Row>
        </View>

        {/* ── Voz ── */}
        <Section title="🎙️ Voz" />
        <View style={styles.card}>
          <Row label="Palavra de ativação">
            <TextInput
              style={styles.smallInput}
              value={wakeWord}
              onChangeText={setWakeWord}
              placeholder="LAS"
              placeholderTextColor={C.muted}
              autoCapitalize="characters"
            />
          </Row>
          <Row label="Escuta contínua">
            <Switch
              value={alwaysListen}
              onValueChange={setAlwaysListen}
              trackColor={{ false: "#333", true: C.primary + "66" }}
              thumbColor={alwaysListen ? C.primary : "#666"}
            />
          </Row>
          {config && (
            <Row label="Backend TTS">
              <Text style={styles.configValue}>{config.tts_backend || "edge-tts"}</Text>
            </Row>
          )}
        </View>

        {/* ── Sistema (somente leitura) ── */}
        {config && (
          <>
            <Section title="⚙️ Sistema" />
            <View style={styles.card}>
              {[
                ["Versão",     config.version],
                ["Provedor",   config.default_provider],
                ["Autonomia",  config.autonomy_level],
                ["Ambiente",   config.app_env || "production"],
              ].map(([k, v]) => (
                <Row key={k} label={k}>
                  <Text style={styles.configValue}>{v}</Text>
                </Row>
              ))}
            </View>
          </>
        )}

        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:      { flex:1, backgroundColor:C.bg },
  header:         { paddingHorizontal:16, paddingVertical:12, borderBottomWidth:1, borderBottomColor:C.border },
  title:          { color:C.text, fontSize:20, fontWeight:"bold" },
  scroll:         { paddingHorizontal:16, paddingTop:16 },
  sectionTitle:   { color:C.muted, fontSize:12, fontWeight:"600", marginTop:20, marginBottom:8,
                    textTransform:"uppercase", letterSpacing:1 },
  card:           { backgroundColor:C.card, borderRadius:14, overflow:"hidden" },
  label:          { color:C.muted, fontSize:12, paddingHorizontal:14, paddingTop:12 },
  urlRow:         { flexDirection:"row", alignItems:"center", padding:12 },
  urlInput:       { flex:1, color:C.text, backgroundColor:"#111", borderRadius:8,
                    paddingHorizontal:12, paddingVertical:8, fontSize:13 },
  testBtn:        { padding:10 },
  testSuccess:    { color:C.success, fontSize:12, paddingHorizontal:14, paddingBottom:10 },
  testError:      { color:C.error, fontSize:12, paddingHorizontal:14, paddingBottom:10 },
  row:            { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                    paddingHorizontal:14, paddingVertical:12, borderTopWidth:1, borderTopColor:"#222" },
  rowLabel:       { color:C.text, fontSize:14 },
  rowValue:       { flexDirection:"row", alignItems:"center", gap:6 },
  themeBtn:       { paddingHorizontal:10, paddingVertical:5, borderRadius:8, backgroundColor:"#111" },
  themeBtnActive: { backgroundColor:C.primary+"44" },
  themeBtnText:   { fontSize:16 },
  themeBtnTextActive: { color:C.primary },
  langBtn:        { paddingHorizontal:8, paddingVertical:4, borderRadius:6, backgroundColor:"#111" },
  langBtnActive:  { borderWidth:1, borderColor:C.primary },
  langText:       { color:C.muted, fontSize:11 },
  smallInput:     { color:C.text, backgroundColor:"#111", borderRadius:8,
                    paddingHorizontal:12, paddingVertical:6, fontSize:13, minWidth:80 },
  configValue:    { color:C.muted, fontSize:13 },
});
