/**
 * useVoice.ts — Hook para captura de voz e TTS
 * Suporta: expo-av (gravação), expo-speech (TTS nativo)
 * Wake word "LAS" via detecção contínua
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { Audio } from "expo-av";
import * as Speech from "expo-speech";
import * as Haptics from "expo-haptics";
import { useAppStore } from "../store/appStore";
import { personalAI } from "../services/api";

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript]   = useState("");
  const [error, setError]             = useState<string | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const { setListening, setSpeaking, wakeWord, alwaysListen, language } = useAppStore();

  // ── Permissão de microfone ─────────────────────────────────────────────────
  useEffect(() => {
    Audio.requestPermissionsAsync().then(({ granted }) => {
      if (!granted) setError("Permissão de microfone negada");
    });
  }, []);

  // ── Inicia gravação ────────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      setError(null);
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      recordingRef.current = recording;
      setIsRecording(true);
      setListening(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (e: any) {
      setError(e.message);
    }
  }, [setListening]);

  // ── Para gravação e transcreve ──────────────────────────────────────────────
  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!recordingRef.current) return null;
    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      recordingRef.current = null;
      setIsRecording(false);
      setListening(false);

      if (!uri) return null;

      // Envia para API (Whisper / STT)
      // Aqui usamos fetch para upload de arquivo binário
      const formData = new FormData();
      formData.append("audio", { uri, type: "audio/m4a", name: "voice.m4a" } as any);

      const baseUrl = useAppStore.getState().serverUrl;
      const resp = await fetch(`${baseUrl}/api/voice/stt`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      const text = data.text || "";
      setTranscript(text);
      return text;
    } catch (e: any) {
      setError(e.message);
      return null;
    } finally {
      setIsRecording(false);
      setListening(false);
    }
  }, [setListening]);

  // ── TTS (Text-to-Speech) ───────────────────────────────────────────────────
  const speak = useCallback(async (text: string, voice?: string) => {
    setSpeaking(true);
    try {
      // Primeiro tenta TTS do servidor (edge-tts quality)
      const baseUrl = useAppStore.getState().serverUrl;
      const resp = await fetch(`${baseUrl}/api/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice }),
      });

      if (resp.ok) {
        // Toca o áudio retornado
        const { sound } = await Audio.Sound.createAsync(
          { uri: resp.url || `${baseUrl}/api/voice/tts?text=${encodeURIComponent(text)}` },
          { shouldPlay: true }
        );
        sound.setOnPlaybackStatusUpdate((status) => {
          if (status.isLoaded && status.didJustFinish) {
            setSpeaking(false);
            sound.unloadAsync();
          }
        });
      } else {
        // Fallback: TTS nativo do dispositivo
        Speech.speak(text, {
          language,
          rate: 1.0,
          onDone: () => setSpeaking(false),
          onError: () => setSpeaking(false),
        });
      }
    } catch (e) {
      // Fallback para TTS nativo
      Speech.speak(text, {
        language,
        rate: 1.0,
        onDone: () => setSpeaking(false),
        onError: () => setSpeaking(false),
      });
    }
  }, [language, setSpeaking]);

  const stopSpeaking = useCallback(() => {
    Speech.stop();
    setSpeaking(false);
  }, [setSpeaking]);

  // ── Wake word detection (simplificado via polling) ─────────────────────────
  // Para produção: integrar com react-native-voice para detecção contínua
  const startWakeWordDetection = useCallback(() => {
    console.log(`Wake word detection iniciado: "${wakeWord}"`);
    // Implementação real: usar react-native-voice com modelo local
  }, [wakeWord]);

  return {
    isRecording,
    transcript,
    error,
    startRecording,
    stopRecording,
    speak,
    stopSpeaking,
    startWakeWordDetection,
  };
}
