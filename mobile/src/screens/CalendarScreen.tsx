/**
 * CalendarScreen.tsx — Calendário com CRUD de eventos
 */
import React, { useState, useEffect } from "react";
import {
  View, Text, TouchableOpacity, ScrollView,
  StyleSheet, Modal, TextInput, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { format, addDays, startOfWeek, isSameDay } from "date-fns";
import { ptBR } from "date-fns/locale";
import { personalAI } from "../services/api";

const C = { bg:"#0f0f0f", card:"#1a1a2e", primary:"#2196f3",
            text:"#e8e8e8", muted:"#888", today:"#6c63ff" };

export default function CalendarScreen() {
  const [selected, setSelected] = useState(new Date());
  const [events, setEvents]     = useState<any[]>([]);
  const [showAdd, setShowAdd]   = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc]   = useState("");
  const [newTime, setNewTime]   = useState("09:00");

  const weekStart = startOfWeek(selected, { locale: ptBR });
  const weekDays  = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  useEffect(() => { loadEvents(); }, [selected]);

  const loadEvents = async () => {
    const dateStr = format(selected, "yyyy-MM-dd");
    const res = await personalAI.getCalendar(dateStr);
    if (res.data?.events) setEvents(res.data.events);
  };

  const addEvent = async () => {
    if (!newTitle.trim()) return;
    const dateStr = format(selected, "yyyy-MM-dd");
    await personalAI.createEvent({
      title: newTitle,
      description: newDesc,
      start_datetime: `${dateStr}T${newTime}:00`,
      end_datetime:   `${dateStr}T${newTime.split(":")[0]}:${String(parseInt(newTime.split(":")[1]) + 30).padStart(2,"0")}:00`,
    });
    setNewTitle(""); setNewDesc(""); setShowAdd(false);
    loadEvents();
  };

  const deleteEvent = (id: string, title: string) => {
    Alert.alert("Excluir evento", `Remover "${title}"?`, [
      { text: "Cancelar", style: "cancel" },
      { text: "Excluir", style: "destructive", onPress: async () => {
          await personalAI.deleteEvent(id);
          loadEvents();
        }},
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Calendário</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* ── Seletor de semana ── */}
      <View style={styles.weekRow}>
        {weekDays.map((d) => {
          const isToday    = isSameDay(d, new Date());
          const isSelected = isSameDay(d, selected);
          return (
            <TouchableOpacity
              key={d.toISOString()}
              style={[styles.dayBtn, isSelected && styles.dayBtnSelected, isToday && styles.dayBtnToday]}
              onPress={() => setSelected(d)}>
              <Text style={[styles.dayName, isSelected && styles.dayNameSel]}>
                {format(d, "EEE", { locale: ptBR }).slice(0,3)}
              </Text>
              <Text style={[styles.dayNum, isSelected && styles.dayNumSel]}>
                {format(d, "d")}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* ── Eventos do dia ── */}
      <View style={styles.dateHeader}>
        <Text style={styles.dateTitle}>
          {format(selected, "EEEE, d 'de' MMMM", { locale: ptBR })}
        </Text>
      </View>

      <ScrollView contentContainerStyle={styles.eventList} showsVerticalScrollIndicator={false}>
        {events.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="calendar-outline" size={48} color={C.muted} />
            <Text style={styles.emptyText}>Sem compromissos</Text>
          </View>
        ) : (
          events.map((ev) => (
            <View key={ev.id} style={styles.eventCard}>
              <View style={styles.eventTime}>
                <Text style={styles.timeText}>
                  {ev.start_datetime ? format(new Date(ev.start_datetime), "HH:mm") : "--:--"}
                </Text>
              </View>
              <View style={styles.eventInfo}>
                <Text style={styles.eventTitle}>{ev.title}</Text>
                {ev.description && <Text style={styles.eventDesc}>{ev.description}</Text>}
                {ev.location && (
                  <View style={styles.locationRow}>
                    <Ionicons name="location-outline" size={12} color={C.muted} />
                    <Text style={styles.locationText}>{ev.location}</Text>
                  </View>
                )}
              </View>
              <TouchableOpacity onPress={() => deleteEvent(ev.id, ev.title)}>
                <Ionicons name="trash-outline" size={16} color="#ff444466" />
              </TouchableOpacity>
            </View>
          ))
        )}
        <View style={{ height: 32 }} />
      </ScrollView>

      {/* ── Modal novo evento ── */}
      <Modal visible={showAdd} transparent animationType="slide">
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Novo Evento</Text>
            <Text style={styles.modalDate}>{format(selected, "dd/MM/yyyy")}</Text>
            <TextInput
              style={styles.input}
              value={newTitle}
              onChangeText={setNewTitle}
              placeholder="Título do evento"
              placeholderTextColor={C.muted}
              autoFocus
            />
            <TextInput
              style={styles.input}
              value={newDesc}
              onChangeText={setNewDesc}
              placeholder="Descrição (opcional)"
              placeholderTextColor={C.muted}
            />
            <TextInput
              style={styles.input}
              value={newTime}
              onChangeText={setNewTime}
              placeholder="Horário (HH:MM)"
              placeholderTextColor={C.muted}
              keyboardType="numbers-and-punctuation"
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAdd(false)}>
                <Text style={{ color: C.muted }}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.saveBtn} onPress={addEvent}>
                <Text style={{ color: "#fff", fontWeight: "600" }}>Salvar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:    { flex:1, backgroundColor:C.bg },
  header:       { flexDirection:"row", justifyContent:"space-between", alignItems:"center",
                  paddingHorizontal:16, paddingVertical:14, borderBottomWidth:1, borderBottomColor:"#222" },
  title:        { color:C.text, fontSize:20, fontWeight:"bold" },
  addBtn:       { backgroundColor:C.primary, borderRadius:20, padding:8 },
  weekRow:      { flexDirection:"row", paddingHorizontal:16, paddingVertical:12, gap:4 },
  dayBtn:       { flex:1, alignItems:"center", paddingVertical:8, borderRadius:10 },
  dayBtnSelected:{ backgroundColor:C.primary },
  dayBtnToday:  { borderWidth:1, borderColor:C.today },
  dayName:      { color:C.muted, fontSize:10, textTransform:"uppercase" },
  dayNameSel:   { color:"#fff" },
  dayNum:       { color:C.text, fontSize:16, fontWeight:"bold", marginTop:2 },
  dayNumSel:    { color:"#fff" },
  dateHeader:   { paddingHorizontal:16, paddingVertical:8 },
  dateTitle:    { color:C.text, fontSize:14, fontWeight:"600", textTransform:"capitalize" },
  eventList:    { paddingHorizontal:16 },
  empty:        { alignItems:"center", paddingTop:40, gap:8 },
  emptyText:    { color:C.muted, fontSize:14 },
  eventCard:    { flexDirection:"row", backgroundColor:C.card, borderRadius:14,
                  padding:14, marginBottom:8, gap:12, alignItems:"flex-start" },
  eventTime:    { minWidth:44 },
  timeText:     { color:C.primary, fontSize:13, fontWeight:"600" },
  eventInfo:    { flex:1 },
  eventTitle:   { color:C.text, fontSize:14, fontWeight:"600" },
  eventDesc:    { color:C.muted, fontSize:12, marginTop:4 },
  locationRow:  { flexDirection:"row", alignItems:"center", gap:4, marginTop:4 },
  locationText: { color:C.muted, fontSize:11 },
  modalBg:      { flex:1, backgroundColor:"#000000aa", justifyContent:"flex-end" },
  modal:        { backgroundColor:C.card, borderTopLeftRadius:20, borderTopRightRadius:20, padding:20 },
  modalTitle:   { color:C.text, fontSize:18, fontWeight:"bold" },
  modalDate:    { color:C.muted, fontSize:13, marginBottom:14 },
  input:        { backgroundColor:"#111", color:C.text, borderRadius:10, padding:12,
                  fontSize:14, marginBottom:10 },
  modalActions: { flexDirection:"row", gap:12, marginTop:4 },
  cancelBtn:    { flex:1, padding:14, borderRadius:12, backgroundColor:"#222", alignItems:"center" },
  saveBtn:      { flex:1, padding:14, borderRadius:12, backgroundColor:C.primary, alignItems:"center" },
});
