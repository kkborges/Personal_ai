/**
 * AppsScreen.tsx — Integração com apps e serviços de streaming
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, TouchableOpacity, FlatList,
  StyleSheet, Linking, Alert, TextInput,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#ff5722", text:"#e8e8e8", muted:"#888" };

const APP_COLORS: Record<string, string> = {
  netflix:"#e50914", "disney+":"#1133b4", "amazon prime":"#00a8e0",
  spotify:"#1db954", youtube:"#ff0000", globoplay:"#ed1c24",
  whatsapp:"#25d366", telegram:"#2ca5e0", "paramount+":"#0064ff",
};

export default function AppsScreen() {
  const [apps, setApps]         = useState<any[]>([]);
  const [search, setSearch]     = useState("");
  const [launching, setLaunching] = useState<string | null>(null);

  useEffect(() => { loadApps(); }, []);

  const loadApps = async () => {
    const res = await personalAI.getApps();
    if (res.data?.apps) setApps(res.data.apps);
  };

  const filtered = apps.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  const launch = async (app: any) => {
    setLaunching(app.id);
    try {
      // Tenta deep link nativo
      const scheme = app.ios_scheme || app.android_package;
      if (scheme) {
        const canOpen = await Linking.canOpenURL(scheme + "://");
        if (canOpen) {
          await Linking.openURL(scheme + "://");
          setLaunching(null);
          return;
        }
      }
      // Fallback: API do servidor
      const res = await personalAI.launchApp(app.id);
      if (res.data?.web_url) await Linking.openURL(res.data.web_url);
      else if (app.web_url)  await Linking.openURL(app.web_url);
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível abrir o app");
    } finally {
      setLaunching(null);
    }
  };

  const renderApp = ({ item }: { item: any }) => {
    const color = APP_COLORS[item.name.toLowerCase()] || C.primary;
    const isLaunching = launching === item.id;
    return (
      <TouchableOpacity
        style={styles.appCard}
        onPress={() => launch(item)}
        disabled={isLaunching}>
        <View style={[styles.appIcon, { backgroundColor: color + "33" }]}>
          <Text style={styles.appEmoji}>{item.icon || "📱"}</Text>
        </View>
        <View style={styles.appInfo}>
          <Text style={styles.appName}>{item.name}</Text>
          <Text style={styles.appCategory}>{item.category || "App"}</Text>
        </View>
        {isLaunching
          ? <View style={[styles.launchBtn, { backgroundColor: color + "33" }]}>
              <Text style={{ fontSize: 12, color }}>Abrindo...</Text>
            </View>
          : <View style={[styles.launchBtn, { backgroundColor: color }]}>
              <Ionicons name="open-outline" size={16} color="#fff" />
            </View>}
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Apps & Serviços</Text>
      </View>

      <View style={styles.searchBar}>
        <Ionicons name="search" size={18} color={C.muted} style={{ marginRight: 8 }} />
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar app..."
          placeholderTextColor={C.muted}
        />
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(a) => a.id || a.name}
        renderItem={renderApp}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        numColumns={1}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>Nenhum app encontrado</Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:  { flex:1, backgroundColor:C.bg },
  header:     { paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:      { color:C.text, fontSize:20, fontWeight:"bold" },
  searchBar:  { flexDirection:"row", alignItems:"center", backgroundColor:C.card,
                marginHorizontal:16, marginVertical:10, borderRadius:12, paddingHorizontal:14, paddingVertical:10 },
  searchInput:{ flex:1, color:C.text, fontSize:14 },
  list:       { paddingHorizontal:16, paddingBottom:24 },
  appCard:    { flexDirection:"row", alignItems:"center", backgroundColor:C.card,
                borderRadius:14, padding:12, marginBottom:8, gap:12 },
  appIcon:    { width:48, height:48, borderRadius:12, alignItems:"center", justifyContent:"center" },
  appEmoji:   { fontSize:24 },
  appInfo:    { flex:1 },
  appName:    { color:C.text, fontSize:15, fontWeight:"600" },
  appCategory:{ color:C.muted, fontSize:12, marginTop:2 },
  launchBtn:  { paddingHorizontal:12, paddingVertical:8, borderRadius:8,
                alignItems:"center", justifyContent:"center" },
  empty:      { alignItems:"center", paddingTop:40 },
  emptyText:  { color:C.muted, fontSize:14 },
});
