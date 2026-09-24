import { Component, type ComponentType, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";
import type { TerrainSceneProps } from "./terrainTypes";

/**
 * Guards §9.6's real 3D scene (TerrainScene.tsx) against a missing native
 * module -- confirmed 2026-09-18 on a real device: `@react-three/fiber` +
 * `expo-gl` throw `TypeError: undefined is not a function` when evaluated
 * inside plain Expo Go (not every native module Expo Go ships is a match
 * for every JS-side library version; this combination isn't one Expo Go's
 * bundled binary supports).
 *
 * The critical bit: that failure happens at MODULE IMPORT time, not at
 * render time -- `import { Canvas } from "@react-three/fiber"` throws
 * while the file is still being evaluated, before any component runs. A
 * React error boundary cannot catch that (it only catches errors thrown
 * during render), and it was cascading into "missing default export"
 * warnings on every route that (transitively) imported this file, which
 * is what took the whole setup wizard down.
 *
 * Fix: `require()` inside a try/catch, at a point in the code that only
 * runs when this module itself is reached -- unlike a static `import`,
 * which Metro hoists to unconditional module-evaluation time with no way
 * to wrap it. This is the standard React Native pattern for an optional
 * native dependency that may not exist in the current runtime.
 *
 * The real fix for actually SEEING the 3D scene is an EAS development
 * build (a personal Expo Go with this project's native modules compiled
 * in) instead of the generic Expo Go app -- Expo Go can only run modules
 * Expo bundled into its own binary ahead of time.
 */
let TerrainSceneImpl: ComponentType<TerrainSceneProps> | null = null;
let loadError: string | null = null;
// Load the 3D stack one layer at a time so a failure NAMES the layer instead
// of a bare "undefined is not a function" (2026-09-21: the installed APK still
// showed that message with no way to tell three, expo-gl, react-three-fiber or
// our own scene apart). Metro needs literal require() arguments.
const LOAD_STEPS: [string, () => unknown][] = [
  ["three", () => require("three")],
  ["expo-gl", () => require("expo-gl")],
  ["@react-three/fiber/native", () => require("@react-three/fiber/native")],
  ["TerrainScene", () => require("./TerrainScene")],
];
for (const [name, load] of LOAD_STEPS) {
  try {
    const mod = load() as { TerrainScene?: ComponentType<TerrainSceneProps> };
    if (name === "TerrainScene") TerrainSceneImpl = mod.TerrainScene ?? null;
  } catch (e) {
    const detail = e instanceof Error ? [e.message, (e.stack ?? "").split("\n")[1]].filter(Boolean).join(" | ") : String(e);
    loadError = `failed at [${name}]: ${detail}`;
    break;
  }
}

/** Render-time failures (a bad scene prop, GL context loss) land here instead
 * of taking the Farm tab down; import-time failures are handled above. */
class SceneBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
  render() {
    if (this.state.error) {
      return (
        <View style={styles.fallback}>
          <Text style={styles.fallbackTitle}>3D view could not start</Text>
          <Text style={styles.fallbackDetail}>{this.state.error}</Text>
        </View>
      );
    }
    return this.props.children;
  }
}

export function SafeTerrainScene(props: TerrainSceneProps) {
  if (!TerrainSceneImpl) {
    return (
      <View style={styles.fallback}>
        <Text style={styles.fallbackTitle}>3D view could not load</Text>
        <Text style={styles.fallbackBody}>
          The 3D terrain needs the installed PepperDex app (not Expo Go). Details below.
        </Text>
        {loadError && <Text style={styles.fallbackDetail}>{loadError}</Text>}
      </View>
    );
  }
  return (
    <SceneBoundary>
      <TerrainSceneImpl {...props} />
    </SceneBoundary>
  );
}

const styles = StyleSheet.create({
  fallback: {
    flex: 1,
    minHeight: 200,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  fallbackTitle: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.brandDark, textAlign: "center" },
  fallbackBody: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, textAlign: "center" },
  fallbackDetail: { fontFamily: fonts.body, fontSize: 10, color: colors.textMuted, textAlign: "center", marginTop: spacing.xs },
});
