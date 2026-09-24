import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";

/** C(n, 2) -- the whole reason the barometer path is worth having. */
export function pairwiseQuestions(n: number): number {
  return n < 2 ? 0 : (n * (n - 1)) / 2;
}

/**
 * Reports barometer status plainly, once known -- restored 2026-09-18 after
 * being dropped from the v2 rebuild (docs/PLAN.md, docs/VALIDATION_CHECKLIST.md
 * log). Mirrors the archived v1 widget (`flutter_app/lib/tier_banner.dart`)
 * exactly: DETECTION is silent and automatic (docs/PROJECT_SPEC.md §4 --
 * the farmer is never asked, never chooses); this only reports the result,
 * framed as a fact about the phone, not a verdict on the farmer. A phone
 * without a barometer is not broken -- it just means more elevation
 * questions during setup, which this banner previews so it isn't a
 * surprise mid-walk.
 */
export function TierBanner({
  status,
  blockCount,
  onRetry,
}: {
  status: "detecting" | "available" | "unavailable";
  blockCount?: number;
  onRetry?: () => void;
}) {
  if (status === "detecting") return null;

  const available = status === "available";
  const accent = available ? colors.brandGreen : colors.warning;
  const n = blockCount ?? 0;
  const questions = pairwiseQuestions(n);

  const fallbackNote =
    n >= 2
      ? `Selepas berjalan, anda akan ditanya ${questions} soalan perbandingan (${n} blok) untuk menentukan arah air.`
      : "Selepas berjalan, anda akan ditanya beberapa soalan perbandingan untuk menentukan arah air.";

  const body = available
    ? "Telefon anda boleh mengesan beza ketinggian sendiri. Ketinggian direkod sepanjang anda berjalan, jadi soalan arah air hanya ditanya bila perlu."
    : `Telefon anda tiada sensor ketinggian, atau ia tidak dapat dibaca sekarang. ${fallbackNote}`;

  return (
    <View style={[styles.card, { borderColor: `${accent}48`, backgroundColor: `${accent}12` }]}>
      <View style={styles.headerRow}>
        <Text style={[styles.title, { color: accent }]}>
          {available ? "Barometer dikesan" : "Tiada barometer"}
        </Text>
        <View style={[styles.pill, { backgroundColor: `${accent}29` }]}>
          <Text style={[styles.pillText, { color: accent }]}>{available ? "OPTIMISED" : "MINIMAL"}</Text>
        </View>
      </View>
      <Text style={styles.body}>{body}</Text>
      {!available && onRetry && (
        <Pressable onPress={onRetry} hitSlop={8}>
          <Text style={[styles.retry, { color: accent }]}>Cuba semula</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.xs },
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { fontFamily: fonts.bodySemi, fontSize: 13, },
  pill: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999 },
  pillText: { fontFamily: fonts.bodySemi, fontSize: 9, },
  body: { fontFamily: fonts.body, fontSize: 12, color: colors.text },
  retry: { fontFamily: fonts.bodySemi, fontSize: 12, marginTop: 4 },
});
