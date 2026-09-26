import { useMemo, useState } from "react";
import { type LayoutChangeEvent, StyleSheet, Text, View } from "react-native";
import Svg, { Line, Polyline } from "react-native-svg";
import { colors, fonts, radius } from "../constants/theme";
import type { WalkMapViewProps } from "./walkMapTypes";

/**
 * Fallback walk map when the Google map is off (no Maps API key in the
 * build). Draws the walked track, numbered block pins and the live position
 * on a light grid with a distance scale -- no internet tiles, so it cannot be
 * blocked (2026-09-27: OpenStreetMap's public tile server returned "403
 * access blocked" on the team's mobile network, though it served the same
 * tiles to the laptop). The real basemap is the Google map (WalkMapView.tsx),
 * enabled by building with a restricted Maps key.
 */

const HEIGHT = 240;
const PAD = 36;
const MIN_SPAN_M = 30; // a single point still shows a sensible neighbourhood

function metresPerDegree(lat: number) {
  return { lat: 111_320, lon: 111_320 * Math.cos((lat * Math.PI) / 180) };
}

function niceScale(maxM: number) {
  const steps = [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000];
  return steps.reduce((best, s) => (s <= maxM ? s : best), steps[0]);
}

export function SchematicWalkMap({ track, blocks, current }: WalkMapViewProps) {
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const view = useMemo(() => {
    const points = [...track, ...blocks.map((b) => ({ lat: b.lat, lon: b.lon })), ...(current ? [current] : [])];
    if (!width || points.length === 0) return null;

    const lat0 = points.reduce((a, p) => a + p.lat, 0) / points.length;
    const m = metresPerDegree(lat0);
    const xs = points.map((p) => p.lon * m.lon);
    const ys = points.map((p) => p.lat * m.lat);
    const spanX = Math.max(MIN_SPAN_M, Math.max(...xs) - Math.min(...xs));
    const spanY = Math.max(MIN_SPAN_M, Math.max(...ys) - Math.min(...ys));
    const pxPerM = Math.min((width - 2 * PAD) / spanX, (HEIGHT - 2 * PAD) / spanY);
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2;
    const cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    const toScreen = (lat: number, lon: number) => ({
      x: width / 2 + (lon * m.lon - cx) * pxPerM,
      y: HEIGHT / 2 - (lat * m.lat - cy) * pxPerM, // north up
    });
    const scaleM = niceScale((width * 0.3) / pxPerM);
    return { toScreen, pxPerM, scaleM };
  }, [width, track, blocks, current]);

  const grid: number[] = [];
  for (let g = 24; g < Math.max(width, HEIGHT); g += 24) grid.push(g);
  const trackPts = view ? track.map((p) => view.toScreen(p.lat, p.lon)) : [];
  const me = view && current ? view.toScreen(current.lat, current.lon) : null;

  return (
    <View style={styles.frame} onLayout={onLayout} accessibilityLabel="Map of your walk and marked blocks">
      <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
        {grid.map((g) => (
          <Line key={`v${g}`} x1={g} y1={0} x2={g} y2={HEIGHT} stroke="#E2DCCB" strokeWidth={1} />
        ))}
        {grid.map((g) => (
          <Line key={`h${g}`} x1={0} y1={g} x2={width} y2={g} stroke="#E2DCCB" strokeWidth={1} />
        ))}
        {trackPts.length > 1 && (
          <Polyline
            points={trackPts.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke={colors.accent}
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {view && (
          <Line
            x1={12}
            y1={HEIGHT - 14}
            x2={12 + view.scaleM * view.pxPerM}
            y2={HEIGHT - 14}
            stroke={colors.brandDark}
            strokeWidth={3}
          />
        )}
      </Svg>

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

      {view && <Text style={styles.scale}>≈{view.scaleM} m</Text>}
      <Text style={styles.north}>N ↑</Text>
      {!view && <Text style={styles.waiting}>Locating…</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { height: HEIGHT, borderRadius: radius.md, overflow: "hidden", backgroundColor: "#FBF9F3" },
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
  scale: { position: "absolute", left: 12, bottom: 20, fontSize: 11, fontFamily: fonts.bodySemi, color: colors.brandDark },
  north: { position: "absolute", right: 10, top: 8, fontSize: 11, fontFamily: fonts.bodySemi, color: colors.textMuted },
  waiting: { position: "absolute", alignSelf: "center", top: HEIGHT / 2 - 10, fontFamily: fonts.body, color: colors.textMuted },
});
