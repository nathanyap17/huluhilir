import { Ionicons } from "@expo/vector-icons";
import { router, Tabs } from "expo-router";
import { Image, Pressable, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts } from "../../src/constants/theme";
import { useT } from "../../src/i18n";

// Trimmed from the real pitch-and-design/PepperDex_Logo.png (transparent
// margins cropped only -- the artwork itself is untouched). Aspect 3.02:1.
const LOGO = require("../../assets/brand/pepperdex-wordmark-header.png");
const LOGO_HEIGHT = 34;

function HeaderLogo() {
  return (
    <Image
      source={LOGO}
      style={styles.logo}
      resizeMode="contain"
      accessibilityLabel="PepperDex Sarawak"
    />
  );
}

/**
 * §9.0 -- rendered once setup is complete. Every tab shows the PepperDex
 * Sarawak logo at the top left instead of the page name (the bottom tab bar
 * still labels Home/Advisor/Farm). Settings is a top-right icon on every tab
 * screen (§9.16, confirmed placement), not a 4th tab.
 */
export default function TabsLayout() {
  const { t } = useT();
  // The phone's own navigation bar (gesture pill or 3 buttons) takes
  // insets.bottom; a fixed tab-bar height hid the tabs under it (2026-09-24).
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        // MOCK_DESIGN.md §7 A.0. Active tab in deep water (text-legible
        // outdoors); headers sit on the paper background, no divider line.
        tabBarActiveTintColor: colors.accentInk,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 58 + Math.max(insets.bottom, 8),
          paddingTop: 6,
          paddingBottom: Math.max(insets.bottom, 8),
        },
        tabBarLabelStyle: { fontFamily: fonts.bodySemi, fontSize: 12 },
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: true,
        sceneStyle: { backgroundColor: colors.background },
        headerTitle: "",
        headerLeft: () => <HeaderLogo />,
        headerRight: () => (
          <Pressable onPress={() => router.push("/settings")} hitSlop={12} style={{ marginRight: 16 }}>
            <Ionicons name="settings-outline" size={22} color={colors.brandDark} />
          </Pressable>
        ),
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tab_home"),
          tabBarIcon: ({ color, size }) => <Ionicons name="water-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="advisor"
        options={{
          title: t("tab_advisor"),
          tabBarIcon: ({ color, size }) => <Ionicons name="chatbubble-ellipses-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="farm"
        options={{
          title: t("tab_farm"),
          tabBarIcon: ({ color, size }) => <Ionicons name="layers-outline" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  logo: { height: LOGO_HEIGHT, width: LOGO_HEIGHT * 3.02, marginLeft: 16 },
});
