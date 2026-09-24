import type { ReactNode } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";
import { colors, radius, shadow, spacing } from "../constants/theme";

/** White surface on the paper background (MOCK_DESIGN.md §5): 20 dp radius,
 * the one soft shadow, 16 dp padding. `quiet` = thin border, no shadow, for
 * supporting cards that must not compete with the Priority action (§7 A.3). */
export function Card({ children, quiet, style }: { children: ReactNode; quiet?: boolean; style?: ViewStyle }) {
  return <View style={[styles.card, quiet ? styles.quiet : shadow.card, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  quiet: {
    borderWidth: 1,
    borderColor: colors.border,
  },
});
