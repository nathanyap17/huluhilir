import { useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { api } from "../../src/api/client";
import { Ionicons } from "@expo/vector-icons";
import { AgentMessage, AgentWorking } from "../../src/components/AgentMessage";
import { LeafVein } from "../../src/components/LeafVein";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import {
  CalendarProposal,
  TreatmentProposalCard,
} from "../../src/components/TreatmentProposalCard";
import { apiBase, withTimeout } from "../../src/constants/config";
import { useSpeak } from "../../src/hooks/useSpeak";
import { useT } from "../../src/i18n";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

interface ChatMessage {
  id: string;
  // "proposals": the approval cards, placed in the conversation where they
  // were produced -- so later messages appear BELOW them, not above.
  role: "user" | "advisor" | "agent" | "proposals";
  proposalIds?: string[];
  proposalRunId?: string;
  text: string;
  citations?: string[];
  isCommand?: boolean;
  verdict?: AdvisorVerdict;
  // role === "agent": one event from GET /agent/runs/{id}/events
  agent?: string;
  kind?: string;
  textMs?: string;
  textEn?: string;
}

interface AdvisorVerdict {
  urgency: "high" | "medium" | "low" | "none";
  reason_code: string;
  reason_ms: string;
}

interface FeedEvent {
  seq: number;
  // Set when the backend merged this step into the previous one from the same
  // agent (one message per agent step, not one per block): drop that message.
  replaces?: number;
  agent: string;
  kind: string;
  text_ms: string;
  text_en: string;
}

interface FeedResponse {
  status: string;
  done: boolean;
  current: { agent: string; text_ms: string; text_en: string } | null;
  events: FeedEvent[];
}

const POLL_MS = 1500;

/**
 * §9.4 (Chat) + §9.5 (Diagnosis Necessity Card) + the live agent feed.
 *
 * "/diagnose" is intercepted client-side and routed to the Advisor verdict
 * (GET /farm/{id}/advisor) -- never straight into a cycle. "Begin Diagnosis"
 * is always enabled (§9.5). After the photo loop (app/diagnosis.tsx) the run
 * continues in the background and this screen receives `runId`: every step
 * the agents actually took (tool calls, council turns, fallback/guard
 * decisions) streams in as a message from that named agent, followed by the
 * schedule proposals awaiting approval. Nothing reaches Google Calendar until
 * the farmer taps Approve on a card (rule 13).
 */
export default function AdvisorScreen() {
  const farm = useSessionStore((s) => s.farm);
  const { t, lang } = useT();
  const { speakText } = useSpeak();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [proposals, setProposals] = useState<CalendarProposal[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [current, setCurrent] = useState<FeedResponse["current"]>(null);
  const inputRef = useRef<TextInput>(null);
  const listRef = useRef<FlatList>(null);
  const lastSeq = useRef(-1);

  const pick = useCallback((ms: string, en: string) => (lang === "en" ? en : ms), [lang]);

  const loadProposals = useCallback(async (): Promise<CalendarProposal[] | null> => {
    if (!farm?.farm_id) return null;
    try {
      const res = await fetch(`${apiBase()}/farms/${farm.farm_id}/calendar-proposals`);
      if (!res.ok) return null;
      const list: CalendarProposal[] = (await res.json()) || [];
      setProposals(list);
      return list;
    } catch {
      // proposals are shown when reachable; the chat still works without them
      return null;
    }
  }, [farm?.farm_id]);

  // On open: load proposals once, and if some still await a decision, show
  // their cards as the first thing in the conversation.
  const shownPending = useRef(false);
  useEffect(() => {
    loadProposals().then((list) => {
      if (shownPending.current || !list) return;
      const pending = list.filter((p) => p.status === "pending_approval").map((p) => p.proposal_id);
      if (pending.length > 0) {
        shownPending.current = true;
        setMessages((m) => [{ id: "pending-cards", role: "proposals", text: "", proposalIds: pending }, ...m]);
      }
    });
  }, [loadProposals]);

  // Shortcut from the Home priority card: "/diagnose" typed but NOT sent.
  const { prefill, n, runId, proposalFor } = useLocalSearchParams<{
    prefill?: string;
    n?: string;
    runId?: string;
    proposalFor?: string;
  }>();

  // Priority card -> "Add to calendar": fetch (or draft) that action's
  // proposal and show its card in the chat for Approve / Reject.
  useEffect(() => {
    if (!proposalFor) return;
    (async () => {
      try {
        const res = await fetch(`${apiBase()}/recommendations/${proposalFor}/calendar-proposal`, { method: "POST" });
        const body = await res.json();
        if (!res.ok) {
          setMessages((m) => [...m, { id: `${Date.now()}-pe`, role: "advisor", text: body?.detail ?? t("advisor_error") }]);
          return;
        }
        setProposals((ps) => [body, ...ps.filter((p) => p.proposal_id !== body.proposal_id)]);
        setMessages((m) => [...m, { id: `${Date.now()}-pc`, role: "proposals", text: "", proposalIds: [body.proposal_id] }]);
      } catch {
        setMessages((m) => [...m, { id: `${Date.now()}-pe`, role: "advisor", text: t("advisor_error") }]);
      }
    })();
  }, [proposalFor, n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (prefill) {
      setInput(prefill);
      inputRef.current?.focus();
    }
  }, [prefill, n]);

  // Arrived from the capture screen with a background run -> follow it.
  useEffect(() => {
    if (!runId || runId === activeRunId) return;
    lastSeq.current = -1;
    setActiveRunId(runId);
    setMessages((m) => [...m, { id: `${runId}-start`, role: "advisor", text: t("feed_started") }]);
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!activeRunId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const res = await fetch(`${apiBase()}/agent/runs/${activeRunId}/events?after=${lastSeq.current}`);
        if (!res.ok || stopped) return;
        const feed: FeedResponse = await res.json();
        if (feed.events.length > 0) {
          lastSeq.current = feed.events[feed.events.length - 1].seq;
          const items: ChatMessage[] = [];
          for (const e of feed.events) {
            items.push({
              id: `${activeRunId}-${e.seq}`,
              role: "agent",
              text: "",
              agent: e.agent,
              kind: e.kind,
              textMs: e.text_ms,
              textEn: e.text_en,
            });
            if (e.kind === "approval") {
              items.push({ id: `${activeRunId}-${e.seq}-cards`, role: "proposals", text: "", proposalRunId: activeRunId });
            }
          }
          const replaced = new Set(
            feed.events.filter((e) => e.replaces != null).map((e) => `${activeRunId}-${e.replaces}`)
          );
          setMessages((m) => [...m.filter((x) => !replaced.has(x.id)), ...items.filter((x) => !replaced.has(x.id))]);
          if (feed.events.some((e) => e.kind === "approval")) loadProposals();
        }
        setCurrent(feed.current);
        if (feed.done) {
          stopped = true;
          setCurrent(null);
          setMessages((m) => [
            ...m,
            {
              id: `${activeRunId}-end`,
              role: "advisor",
              text: feed.status === "failed" ? t("feed_failed") : t("feed_done"),
            },
          ]);
          if (farm?.farm_id) queryClient.invalidateQueries({ queryKey: ["dashboard", farm.farm_id] });
          loadProposals();
        }
      } catch {
        // transient network hiccup: keep polling
      }
    };
    tick();
    const timer = setInterval(() => {
      if (stopped) clearInterval(timer);
      else tick();
    }, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [activeRunId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages.length, current?.text_en, proposals.length]);

  useEffect(() => {
    const sub = Keyboard.addListener("keyboardDidShow", () => {
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 150);
    });
    return () => sub.remove();
  }, []);

  function beginDiagnosis() {
    setMessages((m) => [
      ...m,
      {
        id: `${Date.now()}-dc`,
        role: "agent",
        text: "",
        agent: "diagnosis_coordinator",
        kind: "step",
        textMs: t("feed_step_photos"),
        textEn: t("feed_step_photos"),
      },
    ]);
    router.push("/diagnosis");
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || !farm) return;
    setInput("");

    const isCommand = /^\/diagnose\b/i.test(text);
    setMessages((m) => [...m, { id: `${Date.now()}-u`, role: "user", text, isCommand }]);
    setIsTyping(true);

    try {
      if (isCommand) {
        const { data, error } = await api.GET("/farm/{farm_id}/advisor", {
          params: { path: { farm_id: farm.farm_id! } },
        });
        if (error || !data) throw new Error("advisor unavailable");
        setMessages((m) => [
          ...m,
          {
            id: `${Date.now()}-a`,
            role: "advisor",
            text: data.reason_ms,
            verdict: { urgency: data.urgency, reason_code: data.reason_code, reason_ms: data.reason_ms },
          },
        ]);
      } else {
        // Farm memory: the backend reads this farm's blocks/diagnoses/plan from
        // the DB; the recent turns (incl. the agents' decision) let follow-ups
        // like "does this mean the blocks are safer?" resolve.
        const history = messages
          .filter((m) => m.role !== "agent" || m.kind === "final")
          .slice(-8)
          .map((m) => ({
            role: m.role === "user" ? "user" : "advisor",
            text: m.role === "agent" ? pick(m.textMs ?? "", m.textEn ?? "") : m.text,
          }))
          .filter((h) => h.text);
        const { data, error } = await api.POST("/advisor/ask", {
          body: { question: text, farm_id: farm.farm_id!, history },
          // The local model can take minutes; the backend caps a turn at
          // AGENT_TIMEOUT_S (180 s), so wait a little longer than that
          // instead of the client-wide 15 s limit.
          fetch: (request: Request) => withTimeout(fetch(request), 200_000),
        });
        if (error || !data) throw new Error("advisor unavailable");
        const result = data as { answer: string; sources: string[] };
        setMessages((m) => [
          ...m,
          {
            id: `${Date.now()}-a`,
            role: "advisor",
            text: result.answer || t("advisor_no_answer"),
            citations: result.sources?.filter(Boolean),
          },
        ]);
      }
    } catch {
      setMessages((m) => [...m, { id: `${Date.now()}-e`, role: "advisor", text: t("advisor_error") }]);
    } finally {
      setIsTyping(false);
    }
  }


  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior="padding"
      keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 60}
    >
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
        ListEmptyComponent={<Text style={styles.hint}>{t("advisor_hint")}</Text>}
        ListFooterComponent={
          <View style={styles.footer}>
            {current && <AgentWorking agent={current.agent} text={pick(current.text_ms, current.text_en)} />}
          </View>
        }
        renderItem={({ item }) => {
          if (item.role === "proposals") {
            const cards = proposals.filter((p) =>
              item.proposalIds ? item.proposalIds.includes(p.proposal_id) : p.run_id === item.proposalRunId
            );
            if (cards.length === 0) return null;
            return (
              <View style={styles.proposalsContainer}>
                <Text style={styles.proposalsHeader}>{t("proposals_header")}</Text>
                {cards.map((p) => (
                  <TreatmentProposalCard
                    key={p.proposal_id}
                    proposal={p}
                    onApproved={() => loadProposals()}
                    onRejected={() => loadProposals()}
                  />
                ))}
              </View>
            );
          }
          if (item.role === "agent") {
            const text = pick(item.textMs ?? "", item.textEn ?? "");
            return (
              <AgentMessage
                agent={item.agent ?? "root_agent"}
                kind={item.kind ?? "step"}
                text={text}
                t={t}
                onPress={() => speakText("_adhoc", text)}
              />
            );
          }
          return (
            <View style={[styles.bubble, item.role === "user" ? styles.bubbleUser : styles.bubbleAdvisor]}>
              <Text style={item.role === "user" ? styles.bubbleTextUser : styles.bubbleTextAdvisor}>
                {item.text}
              </Text>
              {item.citations && item.citations.length > 0 && (
                <Text style={styles.citation}>
                  {t("source")}: {item.citations[0]}
                </Text>
              )}
              {item.verdict && (
                // Always enabled, identical whatever the verdict (§9.5 / A.5).
                <View style={styles.beginButton}>
                  <PrimaryButton label={t("begin_diagnosis")} onPress={beginDiagnosis} />
                </View>
              )}
            </View>
          );
        }}
      />
      {isTyping && <ActivityIndicator style={styles.typing} color={colors.accentInk} />}
      <LeafVein />
      <View style={styles.inputRow}>
        <TextInput
          ref={inputRef}
          value={input}
          onChangeText={setInput}
          style={styles.input}
          placeholder={t("advisor_placeholder")}
          onSubmitEditing={handleSend}
          returnKeyType="send"
        />
        <Pressable
          style={({ pressed }) => [styles.sendButton, pressed && styles.sendPressed]}
          onPress={handleSend}
          accessibilityRole="button"
          accessibilityLabel={t("send")}
        >
          <Ionicons name="arrow-up" size={24} color={colors.onAccent} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, gap: 12, flexGrow: 1 },
  footer: { gap: spacing.sm, marginTop: spacing.sm },
  proposalsContainer: { gap: spacing.sm },
  proposalsHeader: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1.2, color: colors.textMuted, textTransform: "uppercase" },
  hint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 15, lineHeight: 22, textAlign: "center", marginTop: spacing.xl, paddingHorizontal: spacing.lg },
  // MOCK_DESIGN.md §7 A.4: farmer right in water (ink text for contrast),
  // Advisor left on white with a thin border. Tails: the corner nearest the
  // speaker is tighter.
  bubble: { maxWidth: "86%", paddingVertical: spacing.sm + 4, paddingHorizontal: spacing.md, borderRadius: radius.md, gap: spacing.xs },
  bubbleUser: { backgroundColor: colors.accent, alignSelf: "flex-end", borderBottomRightRadius: 6 },
  bubbleAdvisor: {
    backgroundColor: colors.surface,
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: colors.border,
    borderBottomLeftRadius: 6,
  },
  bubbleTextUser: { fontFamily: fonts.bodyMedium, color: colors.onAccent, fontSize: 16, lineHeight: 22 },
  bubbleTextAdvisor: { fontFamily: fonts.body, color: colors.text, fontSize: 16, lineHeight: 23 },
  citation: {
    alignSelf: "flex-start",
    fontFamily: fonts.mono,
    fontSize: 11,
    color: colors.textMuted,
    backgroundColor: colors.paperDeep,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  beginButton: { marginTop: spacing.sm },
  typing: { marginBottom: spacing.xs },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.md,
  },
  input: {
    fontFamily: fonts.body,
    flex: 1,
    minHeight: 52,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md + 4,
    paddingVertical: spacing.sm,
    fontSize: 16,
    color: colors.text,
  },
  sendButton: {
    width: 52,
    height: 52,
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  sendPressed: { transform: [{ scale: 0.94 }] },
});
