import { Stack } from "expo-router";

/**
 * Structurally separate from (tabs) -- this stack is the ONLY thing
 * reachable while setup_completed_at is null (docs/PROJECT_SPEC.md §9.0).
 */
export default function SetupLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="welcome" />
      <Stack.Screen name="register" />
      <Stack.Screen name="walk" />
      <Stack.Screen name="elevation" />
      <Stack.Screen name="validator" />
    </Stack>
  );
}
