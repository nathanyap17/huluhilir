import { useState } from "react";
import { LayoutAnimation, Platform, Pressable, StyleSheet, Text, UIManager, View } from "react-native";
import { colors, fonts, radius, shadow, spacing } from "../constants/theme";
import { useSpeak } from "../hooks/useSpeak";
import { useT } from "../i18n";
import { WaterRipple } from "./WaterRipple";

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface DailyForecast {
  date: string;
  rainfall_mm: number;
  is_pulse: boolean;
  is_cached_fallback: boolean;
}

interface RainPulseResponse {
  forecast_days: DailyForecast[];
  station_id: string;
  speech_template_id?: string | null;
}

const DAY_NAMES_MS = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"];
const DAY_NAMES_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function dayLabel(dateStr: string, lang: string = "ms"): string {
  const d = new Date(dateStr);
  return (lang === "en" ? DAY_NAMES_EN : DAY_NAMES_MS)[d.getDay()];
}

function barHeight(mm: number, maxMm: number): number {
  if (maxMm <= 0) return 4;
  return Math.max(4, Math.round((mm / maxMm) * 64));
}

/**
 * §9.1 -- Rain Pulse Card, upgraded from single-day to 7-day
 * (docs/PROJECT_SPEC.md §9.1, §10 RainPulseResponse). "The works with zero
 * photographs claim, made visible every time the app opens" -- this reads
 * only from GET /farms/{id}/dashboard, no diagnosis dependency anywhere.
 *
 * Channeling logic: tapping expands in place (no navigation) to show the
 * full 7-day chart; collapsed state shows only the next pulse.
 */
export function RainPulseCard({ rainPulse }: { rainPulse: RainPulseResponse }) {
  const [expanded, setExpanded] = useState(false);
  const { speak } = useSpeak();
  const { t, lang } = useT();

  const days = rainPulse.forecast_days;
  const nextPulse = days.find((d) => d.is_pulse) ?? days[0];
  const maxMm = Math.max(1, ...days.map((d) => d.rainfall_mm));
  const anyCachedFallback = days.some((d) => d.is_cached_fallback);

  function handlePress() {
    // Spring, not linear (MOCK_DESIGN.md §8) -- the chart opens like water settling.
    LayoutAnimation.configureNext(LayoutAnimation.create(260, "spring", "opacity"));
    setExpanded((v) => !v);
    if (!expanded && rainPulse.speech_template_id && nextPulse) {
      speak(rainPulse.speech_template_id, {
        // slot names must match seed/templates.json rain_pulse_forecast
        // ("Hujan dijangka {rainfall_mm} mm pada {day_slot}.") or the
        // backend answers 422.
        rainfall_mm: nextPulse.rainfall_mm.toFixed(0),
        day_slot: dayLabel(nextPulse.date),
      });
    }
  }

  return (
    <Pressable onPress={handlePress} style={styles.card} accessibilityRole="button" accessibilityHint={t("rain_tap")}>
      <Text style={styles.label}>{t("rain_label")}</Text>

      {!expanded ? (
        nextPulse ? (
          <View style={styles.headlineRow}>
            <Text style={styles.bigNumber}>{nextPulse.rainfall_mm.toFixed(0)}</Text>
            <View style={styles.headlineSide}>
              <Text style={styles.unit}>mm</Text>
              <Text style={styles.day}>{t("rain_day", { day: dayLabel(nextPulse.date, lang) })}</Text>
            </View>
          </View>
        ) : (
          <Text style={styles.sub}>{t("rain_none")}</Text>
        )
      ) : (
        <View style={styles.chartRow}>
          {days.map((d) => (
            <View key={d.date} style={styles.dayColumn}>
              <Text style={styles.dayMm}>{d.rainfall_mm.toFixed(0)}</Text>
              <View
                style={[
                  styles.bar,
                  { height: barHeight(d.rainfall_mm, maxMm) },
                  d.is_pulse && styles.barPulse,
                ]}
              />
              <Text style={styles.dayLabel}>{dayLabel(d.date, lang)}</Text>
            </View>
          ))}
        </View>
      )}

      <WaterRipple color={colors.accentGlow} />

      <View style={styles.footer}>
        {!expanded && nextPulse && <Text style={styles.sub}>{t("rain_tap")}</Text>}
        {anyCachedFallback && <Text style={styles.estimateTag}>{t("rain_estimated")}</Text>}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // MOCK_DESIGN.md §7 A.1: the one dark card on the paper -- the highest
  // priority, always-visible element.
  card: {
    backgroundColor: colors.brandDark,
    borderRadius: radius.md,
    padding: spacing.md,
    paddingBottom: spacing.sm + 4,
    gap: spacing.sm,
    ...shadow.card,
  },
  label: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1.2, color: colors.accentGlow, textTransform: "uppercase" },
  headlineRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
  bigNumber: { fontFamily: fonts.mono, fontSize: 52, lineHeight: 56, color: colors.onDark, letterSpacing: -1 },
  headlineSide: { paddingBottom: 8, gap: 0 },
  unit: { fontFamily: fonts.mono, fontSize: 16, color: colors.accentGlow },
  day: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onDark },
  sub: { fontFamily: fonts.body, fontSize: 13, color: "#C9D6CC" },
  footer: { gap: 2 },
  chartRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
    paddingTop: spacing.sm,
    height: 116,
  },
  dayColumn: { alignItems: "center", gap: 4, flex: 1 },
  bar: { width: 14, backgroundColor: "rgba(127,240,255,0.35)", borderRadius: 7 },
  barPulse: { backgroundColor: colors.accent },
  dayLabel: { fontFamily: fonts.body, fontSize: 11, color: "#C9D6CC" },
  dayMm: { fontFamily: fonts.mono, fontSize: 11, color: colors.onDark },
  estimateTag: { fontFamily: fonts.body, fontSize: 12, color: "#C9D6CC", fontStyle: "italic" },
});
