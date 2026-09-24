import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, fonts, radius, shadow, spacing, stateColor } from "../constants/theme";
import { useSpeak } from "../hooks/useSpeak";
import { useT, type StringKey } from "../i18n";
import { PrimaryButton } from "./PrimaryButton";

interface Drawer {
  risk_score: number;
  confidence: number;
  eta_days?: number | null;
  defer_cause?: string | null;
  rainfall_7d_mm: number;
}

interface TopAction {
  // recommendation_id?: ULID fields carry a Pydantic default_factory, so
  // openapi-typescript marks them optional even though a persisted row
  // always has one set (see app/schemas/common.py ulid_field()).
  recommendation_id?: string;
  block_id: string;
  action_type: string;
  recommended_at: string;
  reason_ms: string;
  speech_template_id?: string | null;
  defer_cause?: string | null;
}

interface AdvisorEvidence {
  last_cycle_result?: string | null;
  days_since_last_cycle: number;
  rain_since_last_cycle_mm: number;
}

interface Tile {
  label: string;
  value: string;
  sub?: string;
  warn?: boolean;
}

const SCHEDULABLE_ACTIONS = new Set(["spray", "drench", "clear_drain"]);

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

/**
 * Bento tiles = the metrics of the latest diagnosis. Risk/confidence/ETA/rain
 * come from the risk_assessments row behind the action (`drawer`, null until
 * compute_spread has actually run for it -- never a placeholder zero). The
 * remaining tiles come from the Advisor's own evidence so a fully-healthy
 * cycle (no spread projection at all) still shows something true.
 */
function buildTiles(
  action: TopAction,
  drawer: Drawer | null,
  advisor: AdvisorEvidence | null,
  t: (key: StringKey, vars?: Record<string, string | number>) => string
): Tile[] {
  const tiles: Tile[] = [];
  if (drawer) {
    tiles.push({ label: t("tile_risk"), value: `${Math.round(drawer.risk_score * 100)}%`, sub: t("sub_estimate") });
    tiles.push({
      label: t("tile_confidence"),
      value: `${Math.round(drawer.confidence * 100)}%`,
      sub: t("sub_input_quality"),
    });
    if (drawer.eta_days != null) {
      tiles.push({ label: t("tile_arrives"), value: `${drawer.eta_days}`, sub: drawer.eta_days === 1 ? t("sub_day") : t("sub_days") });
    }
    tiles.push({ label: t("tile_rain7"), value: `${Math.round(drawer.rainfall_7d_mm)}`, sub: "mm" });
  }
  const deferCause = drawer?.defer_cause ?? action.defer_cause;
  if (deferCause) tiles.push({ label: t("tile_deferred"), value: deferCause, warn: true });
  if (advisor) {
    tiles.push({
      label: t("tile_last_check"),
      value: advisor.days_since_last_cycle === 0 ? t("today") : `${advisor.days_since_last_cycle}d`,
      sub: advisor.last_cycle_result ? t(`result_${advisor.last_cycle_result}` as StringKey) : t("sub_ago"),
    });
    if (!drawer) {
      tiles.push({ label: t("tile_rain_since"), value: `${Math.round(advisor.rain_since_last_cycle_mm)}`, sub: "mm" });
    }
  }
  return tiles;
}

/** Always-on Advisor shortcut: opens the chat with "/diagnose" typed in the
 * box but NOT sent -- the farmer taps send themselves. `n` makes repeated
 * taps count as a fresh request even though the prefill text is identical. */
function goToDiagnose() {
  router.push({ pathname: "/(tabs)/advisor", params: { prefill: "/diagnose", n: String(Date.now()) } });
}

/**
 * §9.2 -- Priority Action Card. ALWAYS rendered (owner preference,
 * 2026-09-19):
 *  - before any diagnosis: a shortcut to start the first one;
 *  - after a diagnosis: the immediate action, the diagnosis metrics as bento
 *    tiles (replacing the old expandable drawer -- nothing to tap to see
 *    them), and a shortcut back to the Advisor for the next /diagnose.
 * Tapping the action text plays the TTS reason; "View block" opens §9.7.
 */
export function PriorityActionCard({
  action,
  drawer,
  advisor,
  blockState,
}: {
  action: TopAction | null;
  drawer: Drawer | null;
  advisor: AdvisorEvidence | null;
  // State of the block this action is for: its colour is the card's left
  // border (MOCK_DESIGN.md §7 A.2) -- colour carries meaning, not decoration.
  blockState?: string | null;
}) {
  const { speakText } = useSpeak();
  const { t } = useT();

  if (!action) {
    return (
      <View style={styles.card}>
        <Text style={styles.label}>{t("priority_label")}</Text>
        <Text style={styles.emptyTitle}>{t("no_diagnosis")}</Text>
        <Text style={styles.sub}>{t("no_diagnosis_body")}</Text>
        <View style={styles.buttonGap}>
          <PrimaryButton label={t("start_first")} onPress={goToDiagnose} />
        </View>
      </View>
    );
  }

  const tiles = buildTiles(action, drawer, advisor, t);
  const when = formatWhen(action.recommended_at);

  return (
    <View style={[styles.card, { borderLeftWidth: 6, borderLeftColor: stateColor[blockState ?? ""] ?? colors.border }]}>
      <Text style={styles.label}>{t("priority_label")}</Text>
      <View style={styles.actionRow}>
        <View style={styles.actionText}>
          <Text style={styles.actionType}>{t(`action_${action.action_type}` as StringKey)}</Text>
          {when !== "" && <Text style={styles.when}>{when}</Text>}
        </View>
        <Pressable
          onPress={() => speakText(action.speech_template_id ?? "_adhoc", action.reason_ms)}
          style={styles.speaker}
          accessibilityRole="button"
          accessibilityLabel={t("listen")}
          hitSlop={4}
        >
          <Ionicons name="volume-medium" size={24} color={colors.onAccent} />
        </Pressable>
      </View>
      <Text style={styles.reason}>{action.reason_ms}</Text>
      {(action.action_type === "spray" || action.action_type === "drench") && (
        <Text style={styles.sourceTag}>{t("from_rules_table")}</Text>
      )}

      {tiles.length > 0 && (
        <View style={styles.bento}>
          {tiles.map((t) => (
            <View key={t.label} style={[styles.tile, t.warn && styles.tileWarn]}>
              <Text style={styles.tileLabel}>{t.label}</Text>
              <Text style={[styles.tileValue, t.warn && styles.tileValueWarn]} numberOfLines={1} adjustsFontSizeToFit>
                {t.value}
              </Text>
              {t.sub != null && <Text style={styles.tileSub}>{t.sub}</Text>}
            </View>
          ))}
        </View>
      )}
      {tiles.length > 0 && <Text style={styles.estimateTag}>{t("estimate_note")}</Text>}

      <View style={styles.linkRow}>
        <Pressable onPress={() => router.push(`/farm/${action.block_id}`)}>
          <Text style={styles.linkText}>{t("view_block")}</Text>
        </Pressable>
        {SCHEDULABLE_ACTIONS.has(action.action_type) && !action.defer_cause && action.recommendation_id && (
          // Opens the Advisor with THIS action's proposal card (drafted on
          // demand if the run didn't leave one pending) for Approve/Reject.
          <Pressable
            onPress={() =>
              router.push({
                pathname: "/(tabs)/advisor",
                params: { proposalFor: action.recommendation_id, n: String(Date.now()) },
              })
            }
          >
            <Text style={styles.linkText}>{t("add_calendar")}</Text>
          </Pressable>
        )}
      </View>

      <View style={styles.buttonGap}>
        <PrimaryButton label={t("diagnose_again")} variant="secondary" onPress={goToDiagnose} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // MOCK_DESIGN.md §7 A.2 -- the hierarchy peak of Home: white surface, the
  // block's state colour as a thick left border, headline in Bricolage.
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.card,
  },
  label: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1.2, color: colors.textMuted, textTransform: "uppercase" },
  emptyTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.text },
  actionRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  actionText: { flex: 1, gap: 2 },
  actionType: { fontFamily: fonts.display, fontSize: 28, lineHeight: 32, color: colors.text },
  when: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.accentInk },
  speaker: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  reason: { fontFamily: fonts.displayBold, fontSize: 17, lineHeight: 23, color: colors.text },
  sub: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21, color: colors.textMuted },
  sourceTag: {
    alignSelf: "flex-start",
    fontFamily: fonts.mono,
    fontSize: 11,
    color: colors.brandDark,
    backgroundColor: colors.paperDeep,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  bento: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  tile: {
    // Grows with its content: a fixed square (aspectRatio 1) overflowed on
    // narrow phones -- "Last check" spilled over the estimate tag (2026-09-24).
    width: "31.5%",
    minHeight: 96,
    backgroundColor: colors.background,
    borderRadius: 16,
    padding: spacing.sm + 2,
    gap: 2,
    justifyContent: "space-between",
  },
  tileWarn: { backgroundColor: "#F6EBDD" },
  tileLabel: { fontFamily: fonts.bodySemi, fontSize: 12, color: colors.textMuted },
  tileValue: { fontFamily: fonts.mono, fontSize: 26, color: colors.brandDark, letterSpacing: -0.5 },
  tileValueWarn: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.warning },
  tileSub: { fontFamily: fonts.body, fontSize: 11, color: colors.textMuted },
  estimateTag: {
    alignSelf: "flex-start",
    fontFamily: fonts.mono,
    fontSize: 11,
    color: colors.textMuted,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  linkRow: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.xs },
  linkText: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.accentInk, paddingVertical: spacing.sm },
  buttonGap: { marginTop: spacing.xs },
});
