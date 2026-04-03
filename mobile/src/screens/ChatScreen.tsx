/**
 * ChatScreen.tsx — Tela principal de chat com IA
 * Features: mensagens em tempo real, voz, modo offline, histórico
 */
import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator,
  StyleSheet, Animated, Vibration,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useAppStore, Message } from "../store/appStore";
import { personalAI, wsManager } from "../services/api";
import { useVoice } from "../hooks/useVoice";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";

const COLORS = {
  bg:        "#0f0f0f",
  card:      "#1a1a2e",
  primary:   "#6c63ff",
  secondary: "#16213e",
  text:      "#e8e8e8",
  muted:     "#888",
  user:      "#6c63ff",
  ai:        "#1e1e3a",
  error:     "#ff4444",
  success:   "#44ff88",
  offline:   "#ff9800",
};

export default function ChatScreen() {
  const { messages, addMessage, conversationId, setConversationId,
          isConnected, pendingOfflineMessages, status } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const micAnim = useRef(new Animated.Value(1)).current;

  const { isRecording, startRecording, stopRecording, speak } = useVoice();

  // ── WebSocket: recebe respostas em tempo real ───────────────────────────────
  useEffect(() => {
    wsManager.connect();
    const unsub = wsManager.on("chat_response", (data) => {
      if (data?.response) {
        const msg: Message = {
          id: `ai_${Date.now()}`,
          role: "assistant",
          content: data.response,
          timestamp: new Date().toISOString(),
          audio_url: data.audio_url,
        };
        addMessage(msg);
        if (data.audio_url || data.response) speak(data.response);
      }
    });
    return () => { unsub(); };
  }, []);

  // ── Scroll para última mensagem ─────────────────────────────────────────────
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages.length]);

  // ── Animação do botão de voz ───────────────────────────────────────────────
  useEffect(() => {
    if (isRecording) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.3, duration: 400, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 1.0, duration: 400, useNativeDriver: true }),
        ])
      ).start();
    } else {
      micAnim.setValue(1);
    }
  }, [isRecording]);

  // ── Envia mensagem de texto ─────────────────────────────────────────────────
  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg) return;

    const userMsg: Message = {
      id: `user_${Date.now()}`,
      role: "user",
      content: msg,
      timestamp: new Date().toISOString(),
    };
    addMessage(userMsg);
    setInput("");
    setLoading(true);

    try {
      const result = await personalAI.sendMessage(msg, conversationId || undefined, false);
      if (result.data) {
        if (result.data.conversation_id && !conversationId) {
          setConversationId(result.data.conversation_id);
        }
        if (!result.offline) {
          const aiMsg: Message = {
            id: `ai_${Date.now()}`,
            role: "assistant",
            content: result.data.response || result.data.message || "...",
            timestamp: new Date().toISOString(),
            offline: false,
          };
          addMessage(aiMsg);
        }
      } else if (result.offline) {
        const offlineMsg: Message = {
          id: `offline_${Date.now()}`,
          role: "assistant",
          content: "⚠️ Sem conexão. Mensagem salva para envio quando você voltar online.",
          timestamp: new Date().toISOString(),
          offline: true,
        };
        addMessage(offlineMsg);
      }
    } catch (e) {
      addMessage({
        id: `err_${Date.now()}`,
        role: "assistant",
        content: "❌ Erro ao enviar mensagem. Tente novamente.",
        timestamp: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
    }
  }, [input, conversationId, addMessage, setConversationId]);

  // ── Envio por voz ──────────────────────────────────────────────────────────
  const handleVoice = useCallback(async () => {
    if (isRecording) {
      const text = await stopRecording();
      if (text) await sendMessage(text);
    } else {
      Vibration.vibrate(50);
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, sendMessage]);

  // ── Renderiza mensagem ─────────────────────────────────────────────────────
  const renderMessage = ({ item }: { item: Message }) => {
    const isUser = item.role === "user";
    const ts = format(new Date(item.timestamp), "HH:mm", { locale: ptBR });

    return (
      <View style={[styles.msgRow, isUser && styles.msgRowUser]}>
        {!isUser && (
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>🤖</Text>
          </View>
        )}
        <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAI,
                       item.offline && styles.bubbleOffline]}>
          <Text style={styles.msgText}>{item.content}</Text>
          <Text style={styles.msgTime}>{ts}{item.offline ? " ·offline" : ""}</Text>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* ── Header ── */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Personal AI</Text>
          <View style={styles.statusRow}>
            <View style={[styles.dot, isConnected ? styles.dotGreen : styles.dotRed]} />
            <Text style={styles.statusText}>
              {isConnected ? `Online · ${status.health_score}%` : "Offline"}
              {pendingOfflineMessages > 0 ? ` · ${pendingOfflineMessages} pendentes` : ""}
            </Text>
          </View>
        </View>
        <TouchableOpacity
          onPress={() => { /* navega para configurações */ }}
          style={styles.headerBtn}>
          <Ionicons name="settings-outline" size={22} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      {/* ── Mensagens ── */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={renderMessage}
        contentContainerStyle={styles.msgList}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>🤖</Text>
            <Text style={styles.emptyText}>Olá! Como posso ajudar?</Text>
            <Text style={styles.emptyHint}>Toque no microfone ou escreva sua mensagem</Text>
          </View>
        }
      />

      {loading && (
        <View style={styles.loadingRow}>
          <ActivityIndicator size="small" color={COLORS.primary} />
          <Text style={styles.loadingText}>Processando...</Text>
        </View>
      )}

      {/* ── Input ── */}
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={90}>
        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Digite sua mensagem..."
            placeholderTextColor={COLORS.muted}
            multiline
            maxLength={2000}
            onSubmitEditing={() => sendMessage()}
            returnKeyType="send"
          />
          <Animated.View style={{ transform: [{ scale: micAnim }] }}>
            <TouchableOpacity
              style={[styles.micBtn, isRecording && styles.micBtnActive]}
              onPress={handleVoice}
              onLongPress={startRecording}>
              <Ionicons
                name={isRecording ? "stop" : "mic"}
                size={24}
                color={isRecording ? "#fff" : COLORS.primary}
              />
            </TouchableOpacity>
          </Animated.View>
          <TouchableOpacity
            style={[styles.sendBtn, !input.trim() && styles.sendBtnDisabled]}
            onPress={() => sendMessage()}
            disabled={!input.trim() || loading}>
            <Ionicons name="send" size={20} color={input.trim() ? "#fff" : COLORS.muted} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: COLORS.bg },
  header:       { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                  paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1,
                  borderBottomColor: "#222" },
  headerTitle:  { color: COLORS.text, fontSize: 20, fontWeight: "bold" },
  statusRow:    { flexDirection: "row", alignItems: "center", marginTop: 2 },
  dot:          { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  dotGreen:     { backgroundColor: COLORS.success },
  dotRed:       { backgroundColor: COLORS.error },
  statusText:   { color: COLORS.muted, fontSize: 12 },
  headerBtn:    { padding: 8 },
  msgList:      { paddingHorizontal: 12, paddingVertical: 8 },
  msgRow:       { flexDirection: "row", marginVertical: 6, alignItems: "flex-end" },
  msgRowUser:   { flexDirection: "row-reverse" },
  avatar:       { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.primary,
                  alignItems: "center", justifyContent: "center", marginHorizontal: 6 },
  avatarText:   { fontSize: 16 },
  bubble:       { maxWidth: "75%", borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleUser:   { backgroundColor: COLORS.user, borderBottomRightRadius: 4 },
  bubbleAI:     { backgroundColor: COLORS.ai, borderBottomLeftRadius: 4 },
  bubbleOffline:{ opacity: 0.7, borderWidth: 1, borderColor: COLORS.offline },
  msgText:      { color: COLORS.text, fontSize: 15, lineHeight: 22 },
  msgTime:      { color: COLORS.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  loadingRow:   { flexDirection: "row", alignItems: "center", justifyContent: "center",
                  padding: 8 },
  loadingText:  { color: COLORS.muted, marginLeft: 8, fontSize: 13 },
  inputBar:     { flexDirection: "row", alignItems: "flex-end", paddingHorizontal: 12,
                  paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#222",
                  backgroundColor: COLORS.bg },
  input:        { flex: 1, backgroundColor: COLORS.secondary, color: COLORS.text,
                  borderRadius: 22, paddingHorizontal: 16, paddingVertical: 10,
                  fontSize: 15, maxHeight: 120, marginRight: 8 },
  micBtn:       { width: 44, height: 44, borderRadius: 22, alignItems: "center",
                  justifyContent: "center", backgroundColor: COLORS.secondary, marginRight: 8 },
  micBtnActive: { backgroundColor: COLORS.error },
  sendBtn:      { width: 44, height: 44, borderRadius: 22, alignItems: "center",
                  justifyContent: "center", backgroundColor: COLORS.primary },
  sendBtnDisabled: { backgroundColor: COLORS.secondary },
  empty:        { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 80 },
  emptyIcon:    { fontSize: 64, marginBottom: 16 },
  emptyText:    { color: COLORS.text, fontSize: 18, fontWeight: "600" },
  emptyHint:    { color: COLORS.muted, fontSize: 13, marginTop: 8 },
});
