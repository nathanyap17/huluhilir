import { Ionicons } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";
import type { StringKey } from "../i18n";

/**
 * One message from a named agent in the Advisor chat (the live feed of
 * GET /agent/runs/{id}/events). Each agent keeps one colour + icon so a
 * farmer can follow who is speaking: the photo loop, the spread model, the
 * rules table, the four council members, the calendar, and the RootAgent
 * that arbitrates. Agent names stay as proper names in every language.
 */
type Persona = { name: string; role: StringKey; icon: keyof typeof Ionicons.glyphMap; color: string };

export const PERSONAS: Record<string, Persona> = {
  diagnosis_coordinator: { name: "DiagnosisCoordinator", role: "agent_role_diagnosis", icon: "camera-outline", color: colors.brandGreen },
  root_agent: { name: "RootAgent", role: "agent_role_root", icon: "git-merge-outline", color: colors.brandDark },
  spread_model: { name: "Spread Model · L2", role: "agent_role_spread", icon: "water-outline", color: "#1d5f8a" },
  rules_table: { name: "Rules Table", role: "agent_role_rules", icon: "book-outline", color: "#6b4f1d" },
  advisor_rag: { name: "Advisor", role: "agent_role_advisor", icon: "library-outline", color: "#4b5d8a" },
  council_agronomic: { name: "Agronomic Urgency", role: "agent_role_council", icon: "leaf-outline", color: colors.stateHarmed },
  council_cost: { name: "Cost Feasibility", role: "agent_role_council", icon: "cash-outline", color: colors.stateAlerted },
  council_logistics: { name: "Logistics", role: "agent_role_council", icon: "walk-outline", color: "#5b6b3a" },
  council_orchestrator: { name: "Council Orchestrator", role: "agent_role_orchestrator", icon: "people-outline", color: colors.stateOverrun },
  calendar_mcp: { name: "Calendar · MCP", role: "agent_role_calendar", icon: "calendar-outline", color: colors.brandLight },
};

export function persona(agent: string): Persona {
  return PERSONAS[agent] ?? PERSONAS.root_agent;
}

export function AgentMessage({
  agent,
  kind,
  text,
  t,
  onPress,
}: {
  agent: string;
  kind: string;
  text: string;
  t: (key: StringKey) => string;
  onPress?: () => void;
}) {
  const p = persona(agent);
  const accent = kind === "warning" ? colors.warning : p.color;
  return (
    <Pressable onPress={onPress} style={[styles.row, kind === "debate" && styles.debateIndent]}>
      <View style={[styles.avatar, { backgroundColor: p.color }]}>
        <Ionicons name={p.icon} size={16} color="#fff" />
      </View>
      <View style={[styles.bubble, { borderLeftColor: accent }, kind === "final" && styles.finalBubble]}>
        <View style={styles.header}>
          <Text style={[styles.name, { color: p.color }]}>{p.name}</Text>
          <Text style={styles.role}>{t(p.role)}</Text>
        </View>
        <Text style={[styles.text, kind === "final" && styles.finalText]}>{text}</Text>
      </View>
    </Pressable>
  );
}

/** The step in flight right now -- replaces the old blind spinner. */
export function AgentWorking({ agent, text }: { agent: string; text: string }) {
  const p = persona(agent);
  return (
    <View style={styles.row}>
      <View style={[styles.avatar, { backgroundColor: p.color, opacity: 0.6 }]}>
        <Ionicons name={p.icon} size={16} color="#fff" />
      </View>
      <View style={styles.working}>
        <ActivityIndicator size="small" color={p.color} />
        <Text style={styles.workingText} numberOfLines={2}>
          <Text style={[styles.name, { color: p.color }]}>{p.name} </Text>
          {text}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, maxWidth: "94%" },
  debateIndent: { marginLeft: spacing.md },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  bubble: {
    flexShrink: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderLeftWidth: 3,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    gap: 2,
  },
  finalBubble: { backgroundColor: "#EAF1E7", borderLeftWidth: 4 },
  header: { flexDirection: "row", alignItems: "baseline", gap: spacing.xs, flexWrap: "wrap" },
  name: { fontFamily: fonts.bodySemi, fontSize: 12, },
  role: { fontFamily: fonts.body, fontSize: 11, color: colors.textMuted },
  text: { fontFamily: fonts.body, fontSize: 14, color: colors.text, lineHeight: 20 },
  finalText: { fontFamily: fonts.bodySemi },
  working: {
    flexShrink: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.border,
  },
  workingText: { fontFamily: fonts.body, flexShrink: 1, fontSize: 13, color: colors.textMuted },
});
