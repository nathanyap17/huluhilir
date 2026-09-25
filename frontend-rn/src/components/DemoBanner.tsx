import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";
import { useT } from "../i18n";
import { leaveToWelcome } from "../session/leaveSession";
import { useSessionStore } from "../store/sessionStore";

/** Ask once, then leave the shared demo farm for the welcome choices. */
export function useLeaveDemo() {
  const { t } = useT();
  return () =>
    Alert.alert(t("leave_demo_title"), t("leave_demo_body"), [
      { text: t("cancel"), style: "cancel" },
      { text: t("leave_demo"), onPress: leaveToWelcome },
    ]);
}

/**
 * Home-screen notice shown only on the shared demo farm, so a visitor who
 * has seen enough can find the way to their own farm without hunting in
 * Settings. Renders nothing on a real farm (the admin phone included).
 */
export function DemoBanner() {
  const { t } = useT();
  const isDemo = useSessionStore((s) => s.isDemo);
  const leaveDemo = useLeaveDemo();
  if (!isDemo) return null;

  return (
    <View style={styles.banner}>
      <Text style={styles.text}>{t("demo_banner")}</Text>
      <Pressable
        onPress={leaveDemo}
        accessibilityRole="button"
        hitSlop={8}
        style={({ pressed }) => [styles.action, pressed && styles.pressed]}
      >
        <Text style={styles.actionLabel}>{t("demo_banner_action")}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  text: { flex: 1, minWidth: 160, fontFamily: fonts.body, fontSize: 14, color: colors.text },
  action: { minHeight: 44, justifyContent: "center" },
  pressed: { opacity: 0.6 },
  actionLabel: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.accentInk, textDecorationLine: "underline" },
});
