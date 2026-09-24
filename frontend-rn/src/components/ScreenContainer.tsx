import type { ReactNode } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from "react-native";
import { colors, spacing } from "../constants/theme";
import { StartOverLink } from "./StartOverLink";
import { VineProgress } from "./VineProgress";

/** Total setup steps shown by the growing vine (register, walk, elevation, check). */
export const SETUP_STEPS = 4;

export function ScreenContainer({ children, setupStep }: { children: ReactNode; setupStep?: number }) {
  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {setupStep != null && <VineProgress step={setupStep} total={SETUP_STEPS} />}
        {setupStep != null && <StartOverLink />}
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

export function ScreenFooter({ children }: { children: ReactNode }) {
  return <View style={styles.footer}>{children}</View>;
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: spacing.md, flexGrow: 1 },
  footer: { padding: spacing.lg, gap: spacing.sm },
});
