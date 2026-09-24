import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../constants/theme";

/**
 * Home's single organic flourish (MOCK_DESIGN.md §6): a thin water line that
 * drifts slowly under the Rain Pulse card. Decorative only -- hidden from
 * screen readers, and still when the phone asks for reduced motion.
 * Drawn twice as wide as its box and translated by exactly one wavelength
 * per loop, so the loop has no visible seam.
 */
const WAVELENGTH = 60;
const WIDTH = WAVELENGTH * 12;

function wavePath(height: number): string {
  const mid = height / 2;
  const amp = height / 2 - 1.5;
  let d = `M0 ${mid}`;
  for (let x = 0; x < WIDTH; x += WAVELENGTH) {
    d += ` Q ${x + WAVELENGTH / 4} ${mid - amp} ${x + WAVELENGTH / 2} ${mid}`;
    d += ` T ${x + WAVELENGTH} ${mid}`;
  }
  return d;
}

export function WaterRipple({ height = 12, color = colors.accent }: { height?: number; color?: string }) {
  const shift = useRef(new Animated.Value(0)).current;
  const [still, setStill] = useState(false);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setStill).catch(() => setStill(false));
  }, []);

  useEffect(() => {
    if (still) return;
    const loop = Animated.loop(
      Animated.timing(shift, {
        toValue: -WAVELENGTH,
        duration: 3200,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    );
    loop.start();
    return () => loop.stop();
  }, [still, shift]);

  return (
    <View style={[styles.clip, { height }]} accessible={false} importantForAccessibility="no-hide-descendants">
      <Animated.View style={{ transform: [{ translateX: shift }] }}>
        <Svg width={WIDTH} height={height}>
          <Path d={wavePath(height)} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" opacity={0.9} />
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  clip: { overflow: "hidden", width: "100%" },
});
