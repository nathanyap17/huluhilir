import "../src/polyfill";
import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useEffect, useState } from "react";
// Per-weight subpaths: the packages' index files require EVERY weight's .ttf,
// which would ship ~30 unused font files inside the APK.
import { BricolageGrotesque_700Bold } from "@expo-google-fonts/bricolage-grotesque/700Bold";
import { BricolageGrotesque_800ExtraBold } from "@expo-google-fonts/bricolage-grotesque/800ExtraBold";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono/500Medium";
import { IBMPlexSans_400Regular } from "@expo-google-fonts/ibm-plex-sans/400Regular";
import { IBMPlexSans_500Medium } from "@expo-google-fonts/ibm-plex-sans/500Medium";
import { IBMPlexSans_600SemiBold } from "@expo-google-fonts/ibm-plex-sans/600SemiBold";
import { useFonts } from "expo-font";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { queryClient } from "../src/api/queryClient";
import { loadApiBase } from "../src/constants/config";
import { colors, fonts } from "../src/constants/theme";

/**
 * Root shell only -- providers + the stack navigator. The actual
 * setup-complete gate lives in app/index.tsx (docs/PROJECT_SPEC.md §9.0):
 * "the tab shell must be structurally unreachable until setup finishes, not
 * just hidden behind a prompt." Routing to (setup) vs (tabs) happens via
 * <Redirect>, not a conditional render here, so a deep link into /(tabs)/...
 * still gets intercepted by index's gate on cold start.
 */
export default function RootLayout() {
  // The saved server address (Settings -> Server address) must be in place
  // before the gate's first request, or a moved laptop means a blank app.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadApiBase().finally(() => setReady(true));
  }, []);
  // Type from MOCK_DESIGN.md §4. A font that fails to load falls back to the
  // system face rather than blocking the app (fontError also ends the wait).
  const [fontsLoaded, fontError] = useFonts({
    BricolageGrotesque_700Bold,
    BricolageGrotesque_800ExtraBold,
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexMono_500Medium,
  });
  if (!ready || (!fontsLoaded && !fontError)) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <AppStack />
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

/**
 * Android draws edge-to-edge (Expo SDK 57): without insets, headerless
 * screens slid under the status bar and bottom buttons under the phone's own
 * navigation bar (reported 2026-09-24). Each screen gets exactly the edges its
 * header / the tab bar don't already cover; the tab bar handles its own.
 * Headers are white, set apart from the paper content (owner request).
 */
function AppStack() {
  const insets = useSafeAreaInsets();
  const bottom = { paddingBottom: insets.bottom };
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: true,
        headerTintColor: colors.brandDark,
        headerTitleStyle: { fontFamily: fonts.displayBold, fontSize: 19 },
        contentStyle: { backgroundColor: colors.background },
        animation: "slide_from_right",
      }}
    >
      <Stack.Screen name="index" />
      <Stack.Screen
        name="(setup)"
        options={{ contentStyle: { backgroundColor: colors.background, paddingTop: insets.top, ...bottom } }}
      />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen
        name="settings"
        options={{ headerShown: true, title: "Settings", contentStyle: { backgroundColor: colors.background, ...bottom } }}
      />
      {/* §9.8 Diagnosis Capture Flow -- reached only from the Advisor's
          "Begin Diagnosis" button (§9.5), so the Advisor gate holds. */}
      <Stack.Screen
        name="diagnosis"
        options={{
          presentation: "modal",
          headerShown: true,
          title: "Diagnosis",
          contentStyle: { backgroundColor: colors.background, ...bottom },
        }}
      />
      <Stack.Screen
        name="farm/[blockId]"
        options={{ headerShown: true, title: "Block", contentStyle: { backgroundColor: colors.background, ...bottom } }}
      />
    </Stack>
  );
}
