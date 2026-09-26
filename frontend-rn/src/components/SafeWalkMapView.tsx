import type { ComponentType } from "react";
import { TileWalkMap } from "./TileWalkMap";
import type { WalkMapViewProps } from "./walkMapTypes";

/**
 * Guards the live walk map (WalkMapView.tsx) against a missing native
 * module -- confirmed 2026-09-18 on a real device: `Error: Cannot find
 * native module 'ExpoMaps'`. Expo Go only ships the native modules Expo
 * pre-bundled into its own binary ahead of time; `expo-maps` isn't one of
 * them in the installed Expo Go build, so it needs an EAS development
 * build instead (a personal Expo Go with this project's native modules
 * compiled in).
 *
 * Same reasoning as SafeTerrainScene.tsx: the failure happens at MODULE
 * IMPORT time (`import { GoogleMaps } from "expo-maps"` throws while the
 * file is still being evaluated), which a React error boundary cannot
 * catch and which was cascading into "missing default export" on every
 * route that imported this file -- taking down the whole setup wizard,
 * not just this one screen. `require()` inside try/catch defers that
 * failure to a point this file's own code controls.
 */
/**
 * 2026-09-20: the standalone `local` APK quit right after registration, when
 * the walk screen first mounted the map. In a real build expo-maps IS
 * compiled in, and Android's GoogleMaps.View crashes the whole process (a
 * native crash, not a JS error, so no try/catch or boundary can stop it)
 * when no Google Maps API key is configured -- and none is. So the native map
 * is opt-in: it only loads when EXPO_PUBLIC_ENABLE_MAP=1, which must be set
 * together with a Maps key in app config. Until then the walk screen shows
 * the position/block readout instead of crashing.
 */
const MAP_ENABLED = process.env.EXPO_PUBLIC_ENABLE_MAP === "1";

let WalkMapViewImpl: ComponentType<WalkMapViewProps> | null = null;
if (MAP_ENABLED) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    WalkMapViewImpl = require("./WalkMapView").WalkMapView;
  } catch {
    WalkMapViewImpl = null;
  }
}

export function SafeWalkMapView(props: WalkMapViewProps) {
  // Default: the key-free OpenStreetMap tile map (what v1 used). The native
  // Google map only when explicitly enabled with a Maps key.
  if (!WalkMapViewImpl) return <TileWalkMap {...props} />;
  return <WalkMapViewImpl {...props} />;
}
