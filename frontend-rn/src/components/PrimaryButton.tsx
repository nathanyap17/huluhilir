import { useRef } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";

interface Props {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "secondary" | "danger";
}

/**
 * Setup requires no typing except optional short block labels (pepperdex-
 * rules skill §8) -- every action in this app should be reachable by a
 * single tap on a large target, never a small icon. This is that target.
 *
 * MOCK_DESIGN.md §5/§8: 56 dp tall, 16 dp radius, water fill with ink text
 * (white on water fails contrast outdoors), and a spring -- not linear --
 * press so the button answers the finger.
 */
export function PrimaryButton({ label, onPress, disabled, loading, variant = "primary" }: Props) {
  const isDisabled = disabled || loading;
  const scale = useRef(new Animated.Value(1)).current;
  const spring = (to: number) =>
    Animated.spring(scale, { toValue: to, useNativeDriver: true, speed: 40, bounciness: 6 }).start();

  const labelColor = variant === "danger" ? "#FFFFFF" : colors.onAccent;
  return (
    <Animated.View style={[styles.wrap, { transform: [{ scale }] }]}>
      <Pressable
        onPress={onPress}
        onPressIn={() => !isDisabled && spring(0.97)}
        onPressOut={() => spring(1)}
        disabled={isDisabled}
        accessibilityRole="button"
        accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
        style={[
          styles.base,
          variant === "secondary" && styles.secondary,
          variant === "danger" && styles.danger,
          isDisabled && styles.disabled,
        ]}
      >
        {loading ? (
          <ActivityIndicator color={labelColor} />
        ) : (
          <Text style={[styles.label, { color: labelColor }]} numberOfLines={2}>
            {label}
          </Text>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexShrink: 1 },
  base: {
    backgroundColor: colors.accent,
    paddingVertical: spacing.sm + 6,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.button,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 56,
  },
  secondary: {
    backgroundColor: colors.surface,
    borderWidth: 1.5,
    borderColor: colors.brandDark,
  },
  danger: {
    backgroundColor: colors.danger,
  },
  disabled: {
    opacity: 0.45,
  },
  label: {
    fontFamily: fonts.bodySemi,
    fontSize: 16,
    textAlign: "center",
  },
});
