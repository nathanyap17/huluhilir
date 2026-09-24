import { GoogleMaps } from "expo-maps";
import { useRef, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius, spacing } from "../constants/theme";
import type { WalkMapViewProps } from "./walkMapTypes";

export type { WalkMapBlock } from "./walkMapTypes";

/**
 * Live map for the walk -- restored 2026-09-18 (see
 * `flutter_app/lib/walk_map.dart`'s `WalkMap`, dropped from the v2 rebuild;
 * docs/VALIDATION_CHECKLIST.md log). The point is orientation, not
 * surveying: a farmer needs to see the app is actually following them and
 * which corners of the garden are already marked. Draws the walked track
 * and marked points ONLY -- no boundary, polygon, or parcel outline is
 * ever drawn, inferred, or stored (rule 4, NCR land is legally sensitive).
 *
 * Uses `expo-maps` (official Expo SDK package, Expo-Go-compatible) rather
 * than the v1 Flutter build's `flutter_map` + raw OpenStreetMap tiles, or
 * the community `react-native-maps` (which needs a custom dev client, not
 * plain Expo Go) -- Android only for now, matching this project's Android-
 * first stack decision (docs/CLAUDE.md). expo-maps has no persistent
 * numbered-pin icon API (GoogleMapsMarker.icon needs a pre-rendered image
 * asset) -- each block's rank/label shows in its tap callout instead of
 * being etched on the pin itself, a smaller but honest substitute.
 */
export function WalkMapView({ track, blocks, current }: WalkMapViewProps) {
  const [follow, setFollow] = useState(true);
  const mapRef = useRef<GoogleMaps.MapView>(null);

  if (Platform.OS !== "android") {
    return (
      <View style={styles.unsupported}>
        <Text style={styles.unsupportedText}>
          Live map is Android-only for now -- your blocks are still being saved normally.
        </Text>
      </View>
    );
  }

  const centre = current ?? track[track.length - 1] ?? { lat: 1.5533, lon: 110.3592 };

  return (
    <View style={styles.container}>
      <GoogleMaps.View
        ref={mapRef}
        style={styles.map}
        cameraPosition={{ coordinates: { latitude: centre.lat, longitude: centre.lon }, zoom: 17 }}
        userLocation={current ? { coordinates: { latitude: current.lat, longitude: current.lon }, followUserLocation: follow } : undefined}
        properties={{ isMyLocationEnabled: true }}
        uiSettings={{ myLocationButtonEnabled: false, compassEnabled: true, zoomControlsEnabled: false }}
        polylines={
          track.length > 1
            ? [
                {
                  id: "track",
                  coordinates: track.map((p) => ({ latitude: p.lat, longitude: p.lon })),
                  color: colors.berryRed,
                  width: 4,
                },
              ]
            : []
        }
        markers={blocks.map((b) => ({
          id: b.block_id,
          coordinates: { latitude: b.lat, longitude: b.lon },
          title: b.rank != null ? `#${b.rank} ${b.label}` : b.label,
          showCallout: true,
        }))}
        onCameraMove={() => {
          // Best-effort: any camera move event while following is either
          // the programmatic follow itself or a manual pan -- expo-maps
          // does not currently distinguish the two. A persistent toggle
          // (below) is the honest way to let a farmer stop/resume
          // following without depending on that ambiguity.
        }}
      />
      <Pressable
        style={[styles.followButton, follow && styles.followButtonActive]}
        onPress={() => setFollow((v) => !v)}
      >
        <Text style={[styles.followButtonText, follow && styles.followButtonTextActive]}>
          {follow ? "Mengikut lokasi" : "Ikut lokasi"}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { height: 240, borderRadius: radius.md, overflow: "hidden" },
  map: { flex: 1 },
  unsupported: {
    height: 120,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.md,
  },
  unsupportedText: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted, textAlign: "center" },
  followButton: {
    position: "absolute",
    right: spacing.sm,
    bottom: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: radius.lg,
    paddingVertical: 6,
    paddingHorizontal: spacing.sm,
  },
  followButtonActive: { backgroundColor: colors.brandGreen },
  followButtonText: { fontFamily: fonts.bodySemi, fontSize: 11, color: colors.brandDark },
  followButtonTextActive: { color: "#fff" },
});
