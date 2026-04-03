/**
 * _layout.tsx — Layout raiz do Expo Router
 */
import { useEffect } from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as SplashScreen from "expo-splash-screen";
import * as Notifications from "expo-notifications";
import NetInfo from "@react-native-community/netinfo";
import { useAppStore } from "../src/store/appStore";
import { wsManager, syncOfflineQueue } from "../src/services/api";

SplashScreen.preventAutoHideAsync();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function RootLayout() {
  const { setConnected, setPendingOffline, serverUrl } = useAppStore();

  useEffect(() => {
    // Monitora conectividade
    const unsub = NetInfo.addEventListener((state) => {
      const online = state.isConnected ?? false;
      setConnected(online);
      if (online) {
        syncOfflineQueue().then((count) => {
          if (count > 0) console.log(`Sincronizados ${count} itens offline`);
        });
      }
    });

    // Conecta WebSocket
    wsManager.connect();
    wsManager.on("metrics", (data) => {
      useAppStore.getState().updateStatus({
        cpu_percent:    data.cpu_percent,
        memory_percent: data.memory_percent,
        health_score:   data.health_score,
        online:         data.online,
        pending_sync:   data.pending_sync,
      });
    });

    // Esconde splash
    SplashScreen.hideAsync();

    return () => {
      unsub();
      wsManager.disconnect();
    };
  }, []);

  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="+not-found" />
      </Stack>
    </>
  );
}
