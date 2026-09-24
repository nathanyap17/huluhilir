import { StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../constants/theme";

/**
 * Compact live altitude readout for the walk screen -- restored 2026-09-18
 * (see `flutter_app/lib/tier_banner.dart`'s `AltitudeReadout`). Relative to
 * the walk session's pressure baseline, never an absolute altitude -- a
 * phone barometer cannot honestly claim one. OPTIMISED tier only; shows
 * "-- m" rather than a fabricated number when unavailable.
 */
export function AltitudeReadout({ relativeM }: { relativeM: number | null }) {
  const has = relativeM != null;
  return (
    <View style={styles.row}>
      <Text style={[styles.value, { color: has ? colors.brandGreen : colors.textMuted }]}>
        {has ? `${relativeM! >= 0 ? "+" : ""}${relativeM!.toFixed(1)} m` : "— m"}
      </Text>
      <Text style={styles.label}>dari mula</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "baseline", gap: 4 },
  value: { fontFamily: fonts.bodySemi, fontSize: 13, },
  label: { fontFamily: fonts.body, fontSize: 10, color: colors.textMuted },
});
