import { useMemo, useState } from "react";
import { Image, type LayoutChangeEvent, StyleSheet, Text, View } from "react-native";
import Svg, { Polyline } from "react-native-svg";
import { colors, fonts, radius } from "../constants/theme";
import type { WalkMapViewProps } from "./walkMapTypes";

/**
 * Live walk map drawn from OpenStreetMap tiles -- the same source the v1
 * Flutter app used (flutter_map + tile.openstreetmap.org), restored
 * 2026-09-27. Plain <Image> tiles and an SVG overlay: no native map module
 * and no API key, so it cannot hit the Google Maps no-key crash that forced
 * the native map off (see SafeWalkMapView.tsx).
 *
 * Auto-fits the walked track, the marked blocks and the current position.
 * A tile that fails to load (no signal on the hillside) just leaves the grey
 * background: the markers and track still draw, and marking a block never
 * depends on a tile arriving.
 */

const TILE = 256;
const MAX_ZOOM = 19;
const MIN_ZOOM = 14;
const HEIGHT = 240;
const PAD = 36;
const TILE_URL = (z: number, x: number, y: number) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
// OSM tile policy: identify the app; attribution must be visible (below).
const TILE_HEADERS = { "User-Agent": "PepperDex/1.0 (my.agrohack.pepperdex)" };

function project(lat: number, lon: number, z: number) {
  const scale = TILE * 2 ** z;
  const sin = Math.sin((Math.max(-85, Math.min(85, lat)) * Math.PI) / 180);
  return {
    x: ((lon + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
  };
}

export function TileWalkMap({ track, blocks, current }: WalkMapViewProps) {
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const view = useMemo(() => {
    const points = [
      ...track,
      ...blocks.map((b) => ({ lat: b.lat, lon: b.lon })),
      ...(current ? [current] : []),
    ];
    if (!width || points.length === 0) return null;

    // Highest zoom at which everything fits inside the padded frame.
    let zoom = MAX_ZOOM;
    for (; zoom > MIN_ZOOM; zoom--) {
      const px = points.map((p) => project(p.lat, p.lon, zoom));
      const w = Math.max(...px.map((p) => p.x)) - Math.min(...px.map((p) => p.x));
      const h = Math.max(...px.map((p) => p.y)) - Math.min(...px.map((p) => p.y));
      if (w <= width - 2 * PAD && h <= HEIGHT - 2 * PAD) break;
    }
    const px = points.map((p) => project(p.lat, p.lon, zoom));
    const cx = (Math.max(...px.map((p) => p.x)) + Math.min(...px.map((p) => p.x))) / 2;
    const cy = (Math.max(...px.map((p) => p.y)) + Math.min(...px.map((p) => p.y))) / 2;
    const left = cx - width / 2;
    const top = cy - HEIGHT / 2;
    const toScreen = (lat: number, lon: number) => {
      const p = project(lat, lon, zoom);
      return { x: p.x - left, y: p.y - top };
    };

    const tiles: { key: string; uri: string; x: number; y: number }[] = [];
    const n = 2 ** zoom;
    for (let tx = Math.floor(left / TILE); tx <= Math.floor((left + width) / TILE); tx++) {
      for (let ty = Math.floor(top / TILE); ty <= Math.floor((top + HEIGHT) / TILE); ty++) {
        if (ty < 0 || ty >= n) continue;
        const wx = ((tx % n) + n) % n;
        tiles.push({ key: `${zoom}/${tx}/${ty}`, uri: TILE_URL(zoom, wx, ty), x: tx * TILE - left, y: ty * TILE - top });
      }
    }
    return { tiles, toScreen };
  }, [width, track, blocks, current]);

  const trackPoints = view ? track.map((p) => view.toScreen(p.lat, p.lon)) : [];
  const me = view && current ? view.toScreen(current.lat, current.lon) : null;

  return (
    <View style={styles.frame} onLayout={onLayout} accessibilityLabel="Map of your walk and marked blocks">
      {view?.tiles.map((t) => (
        <Image
          key={t.key}
          source={{ uri: t.uri, headers: TILE_HEADERS }}
          style={[styles.tile, { left: t.x, top: t.y }]}
          fadeDuration={0}
        />
      ))}

      {view && trackPoints.length > 1 && (
        <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
          <Polyline
            points={trackPoints.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke={colors.accent}
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </Svg>
      )}

      {view &&
        blocks.map((b, i) => {
          const p = view.toScreen(b.lat, b.lon);
          return (
            <View key={b.block_id} style={[styles.block, { left: p.x - 13, top: p.y - 13 }]}>
              <Text style={styles.blockText}>{i + 1}</Text>
            </View>
          );
        })}

      {me && <View style={[styles.me, { left: me.x - 8, top: me.y - 8 }]} />}

      {!view && <Text style={styles.waiting}>Locating…</Text>}
      <Text style={styles.attribution}>© OpenStreetMap contributors</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    height: HEIGHT,
    borderRadius: radius.md,
    overflow: "hidden",
    backgroundColor: "#E4E0D4",
  },
  tile: { position: "absolute", width: TILE, height: TILE },
  block: {
    position: "absolute",
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.brandDark,
    borderWidth: 2,
    borderColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  blockText: { color: "#FFFFFF", fontFamily: fonts.bodySemi, fontSize: 12 },
  me: {
    position: "absolute",
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: colors.accent,
    borderWidth: 3,
    borderColor: "#FFFFFF",
  },
  waiting: {
    position: "absolute",
    alignSelf: "center",
    top: HEIGHT / 2 - 10,
    fontFamily: fonts.body,
    color: colors.textMuted,
  },
  attribution: {
    position: "absolute",
    right: 6,
    bottom: 4,
    fontSize: 10,
    fontFamily: fonts.body,
    color: "#333",
    backgroundColor: "rgba(255,255,255,0.75)",
    paddingHorizontal: 4,
    borderRadius: 4,
  },
});
