import { Alert, Pressable, StyleSheet, Text } from "react-native";
import { colors, fonts, spacing } from "../constants/theme";
import { useT } from "../i18n";
import { leaveToWelcome } from "../session/leaveSession";
import { useSessionStore } from "../store/sessionStore";

/**
 * The way out of an unfinished setup. The gate (app/index.tsx) sends a phone
 * with an incomplete farm straight back to the walk on every start, so
 * without this a farmer who tapped "Set up my farm" by mistake -- or wants
 * the demo instead -- could never reach the welcome choices again.
 *
 * Only this phone's session is cleared; nothing is deleted on the server.
 * Renders nothing until a farm exists (register has the system back button).
 */
export function StartOverLink() {
  const { t } = useT();
  const hasFarm = useSessionStore((s) => !!s.farm);
  if (!hasFarm) return null;

  function confirm() {
    Alert.alert(t("start_over_title"), t("start_over_body"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("start_over"),
        style: "destructive",
        onPress: leaveToWelcome,
      },
    ]);
  }

  return (
    <Pressable
      onPress={confirm}
      accessibilityRole="button"
      hitSlop={8}
      style={({ pressed }) => [styles.link, pressed && styles.pressed]}
    >
      <Text style={styles.label}>{t("start_over")}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  link: {
    alignSelf: "flex-end",
    minHeight: 48,
    justifyContent: "center",
    paddingHorizontal: spacing.sm,
  },
  pressed: { opacity: 0.6 },
  label: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.accentInk, textDecorationLine: "underline" },
});
