/**
 * AppNavigator.tsx — Navegação principal do app
 */
import React from "react";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createStackNavigator }    from "@react-navigation/stack";
import { NavigationContainer }     from "@react-navigation/native";
import { Ionicons }                from "@expo/vector-icons";
import { StatusBar }               from "expo-status-bar";

import HomeScreen     from "../screens/HomeScreen";
import ChatScreen     from "../screens/ChatScreen";

// Lazy-loaded screens
const MemoryScreen    = React.lazy(() => import("../screens/MemoryScreen"));
const CalendarScreen  = React.lazy(() => import("../screens/CalendarScreen"));
const RoutinesScreen  = React.lazy(() => import("../screens/RoutinesScreen"));
const BluetoothScreen = React.lazy(() => import("../screens/BluetoothScreen"));
const AppsScreen      = React.lazy(() => import("../screens/AppsScreen"));
const MonitorScreen   = React.lazy(() => import("../screens/MonitorScreen"));
const SettingsScreen  = React.lazy(() => import("../screens/SettingsScreen"));

const Tab   = createBottomTabNavigator();
const Stack = createStackNavigator();

const COLORS = {
  bg:      "#0f0f0f",
  card:    "#1a1a2e",
  primary: "#6c63ff",
  text:    "#e8e8e8",
  muted:   "#555",
};

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: {
          backgroundColor: COLORS.card,
          borderTopColor: "#2a2a4a",
          height: 60,
          paddingBottom: 8,
        },
        tabBarActiveTintColor:   COLORS.primary,
        tabBarInactiveTintColor: COLORS.muted,
        tabBarIcon: ({ focused, color, size }) => {
          const icons: Record<string, any> = {
            Home:     focused ? "home"             : "home-outline",
            Chat:     focused ? "chatbubbles"      : "chatbubbles-outline",
            Memory:   focused ? "brain"            : "brain-outline",
            Calendar: focused ? "calendar"         : "calendar-outline",
            Settings: focused ? "settings"         : "settings-outline",
          };
          return <Ionicons name={icons[route.name] || "ellipse"} size={size} color={color} />;
        },
      })}>
      <Tab.Screen name="Home"     component={HomeScreen}     options={{ title: "Início" }} />
      <Tab.Screen name="Chat"     component={ChatScreen}     options={{ title: "Chat" }} />
      <Tab.Screen name="Memory"   component={React.lazy(() => import("../screens/MemoryScreen"))}   options={{ title: "Memória" }} />
      <Tab.Screen name="Calendar" component={React.lazy(() => import("../screens/CalendarScreen"))} options={{ title: "Calendário" }} />
      <Tab.Screen name="Settings" component={React.lazy(() => import("../screens/SettingsScreen"))} options={{ title: "Ajustes" }} />
    </Tab.Navigator>
  );
}

export default function AppNavigator() {
  return (
    <NavigationContainer
      theme={{
        dark: true,
        colors: {
          primary:    COLORS.primary,
          background: COLORS.bg,
          card:       COLORS.card,
          text:       COLORS.text,
          border:     "#2a2a4a",
          notification: COLORS.primary,
        },
      }}>
      <StatusBar style="light" />
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Main"      component={MainTabs} />
        <Stack.Screen name="Bluetooth" component={React.lazy(() => import("../screens/BluetoothScreen"))} />
        <Stack.Screen name="Routines"  component={React.lazy(() => import("../screens/RoutinesScreen"))} />
        <Stack.Screen name="Apps"      component={React.lazy(() => import("../screens/AppsScreen"))} />
        <Stack.Screen name="Monitor"   component={React.lazy(() => import("../screens/MonitorScreen"))} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
