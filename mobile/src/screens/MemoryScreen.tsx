/**
 * MemoryScreen.tsx — Browser de memórias de longo prazo
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, FlatList, TextInput, TouchableOpacity,
  StyleSheet, Alert, Modal,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#9c27b0",
            text:"#e8e8e8", muted:"#888", success:"#44ff88", error:"#ff4444" };

export default function MemoryScreen() {
  const [memories, setMemories] = useState<any[]>([]);
  const [query, setQuery]       = useState("");
  const [showAdd, setShowAdd]   = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType]   = useState<"fact"|"preference"|"event">("fact");

  useEffect(() => { loadMemories(); }, []);

  const loadMemories = async (q?: string) => {
    const res = await personalAI.getMemories(q);
    if (res.data?.memories) setMemories(res.data.memories);
  };

  const addMemory = async () => {
    if (!newContent.trim()) return;
    await personalAI.addMemory(newContent, newType, 0.8);
    setNewContent(""); setShowAdd(false);
    loadMemories();
  };

  const deleteMemory = (id: string) => {
    Alert.alert("Excluir", "Remover esta memória?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Excluir", style: "destructive", onPress: async () => {
          await personalAI.deleteMemory(id);
          loadMemories();
        }},
    ]);
  };

  const typeColor = (t: string) =>
    ({ fact:"#2196f3", preference:"#9c27b0", event:"#4caf50", task:"#ff9800" }[t] || C.primary);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Memória</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      <View style={styles.searchBar}>
        <Ionicons name="search" size={16} color={C.muted} style={{ marginRight: 8 }} />
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={(t) => { setQuery(t); if (t.length > 2) loadMemories(t); }}
          placeholder="Buscar memórias..."
          placeholderTextColor={C.muted}
          onSubmitEditing={() => loadMemories(query)}
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => { setQuery(""); loadMemories(); }}>
            <Ionicons name="close-circle" size={16} color={C.muted} />
          </TouchableOpacity>
        )}
      </View>

      <FlatList
        data={memories}
        keyExtractor={(m) => m.id}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <View style={[styles.typeBadge, { backgroundColor: typeColor(item.type) + "33" }]}>
                <Text style={[styles.typeText, { color: typeColor(item.type) }]}>{item.type}</Text>
              </View>
              <Text style={styles.importance}>⭐ {(item.importance * 10).toFixed(0)}/10</Text>
              <TouchableOpacity onPress={() => deleteMemory(item.id)}>
                <Ionicons name="trash-outline" size={16} color={C.error} />
              </TouchableOpacity>
            </View>
            <Text style={styles.content}>{item.content}</Text>
            {item.tags?.length > 0 && (
              <View style={styles.tags}>
                {(typeof item.tags === "string" ? JSON.parse(item.tags) : item.tags).map((tag: string) => (
                  <View key={tag} style={styles.tag}>
                    <Text style={styles.tagText}>{tag}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="brain-outline" size={48} color={C.muted} />
            <Text style={styles.emptyText}>Sem memórias ainda</Text>
          </View>
        }
      />

      {/* ── Modal adicionar ── */}
      <Modal visible={showAdd} transparent animationType="slide">
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Nova Memória</Text>
            <TextInput
              style={styles.modalInput}
              value={newContent}
              onChangeText={setNewContent}
              placeholder="O que devo lembrar?"
              placeholderTextColor={C.muted}
              multiline
              autoFocus
            />
            <View style={styles.typeRow}>
              {(["fact","preference","event"] as const).map((t) => (
                <TouchableOpacity
                  key={t}
                  style={[styles.typeBtn, newType === t && { backgroundColor: typeColor(t) }]}
                  onPress={() => setNewType(t)}>
                  <Text style={[styles.typeBtnText, newType === t && { color: "#fff" }]}>{t}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancel} onPress={() => setShowAdd(false)}>
                <Text style={styles.modalCancelText}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSave} onPress={addMemory}>
                <Text style={styles.modalSaveText}>Salvar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:   { flex:1, backgroundColor:C.bg },
  header:      { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                 paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:       { color:C.text, fontSize:20, fontWeight:"bold" },
  addBtn:      { backgroundColor:C.primary, borderRadius:20, padding:8 },
  searchBar:   { flexDirection:"row", alignItems:"center", backgroundColor:C.card,
                 marginHorizontal:16, marginVertical:10, borderRadius:12, paddingHorizontal:14, paddingVertical:10 },
  searchInput: { flex:1, color:C.text, fontSize:14 },
  list:        { paddingHorizontal:16, paddingBottom:24 },
  card:        { backgroundColor:C.card, borderRadius:14, padding:14, marginBottom:8 },
  cardHeader:  { flexDirection:"row", alignItems:"center", marginBottom:8, gap:8 },
  typeBadge:   { paddingHorizontal:8, paddingVertical:3, borderRadius:6 },
  typeText:    { fontSize:11, fontWeight:"600" },
  importance:  { flex:1, color:C.muted, fontSize:12 },
  content:     { color:C.text, fontSize:14, lineHeight:20 },
  tags:        { flexDirection:"row", flexWrap:"wrap", gap:4, marginTop:8 },
  tag:         { backgroundColor:"#222", paddingHorizontal:8, paddingVertical:3, borderRadius:6 },
  tagText:     { color:C.muted, fontSize:11 },
  empty:       { alignItems:"center", paddingTop:60, gap:12 },
  emptyText:   { color:C.muted, fontSize:14 },
  modalBg:     { flex:1, backgroundColor:"#000000aa", justifyContent:"flex-end" },
  modal:       { backgroundColor:C.card, borderTopLeftRadius:20, borderTopRightRadius:20, padding:20 },
  modalTitle:  { color:C.text, fontSize:18, fontWeight:"bold", marginBottom:16 },
  modalInput:  { backgroundColor:"#111", color:C.text, borderRadius:10, padding:14,
                 fontSize:14, minHeight:80, textAlignVertical:"top", marginBottom:12 },
  typeRow:     { flexDirection:"row", gap:8, marginBottom:16 },
  typeBtn:     { paddingHorizontal:14, paddingVertical:7, borderRadius:20, backgroundColor:"#222" },
  typeBtnText: { color:C.muted, fontSize:13 },
  modalActions:{ flexDirection:"row", gap:12 },
  modalCancel: { flex:1, padding:14, borderRadius:12, backgroundColor:"#222", alignItems:"center" },
  modalCancelText: { color:C.muted, fontSize:14 },
  modalSave:   { flex:1, padding:14, borderRadius:12, backgroundColor:C.primary, alignItems:"center" },
  modalSaveText: { color:"#fff", fontSize:14, fontWeight:"600" },
});
