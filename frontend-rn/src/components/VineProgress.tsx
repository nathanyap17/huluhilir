import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../constants/theme";

/**
 * The setup wizard's flourish (MOCK_DESIGN.md §6, §7 A.9-A.13): one vine that
 * grows across the whole wizard -- a leaf per step -- instead of a numbered
 * progress bar. Farmers count what is done, not percentages.
 *
 * A faint full vine is drawn once; a vivid copy is revealed by a clip whose
 * width springs from the previous step to this one. Reduced motion: no spring.
 */
const HEIGHT = 40;

function vinePath(width: number, steps: number): { stem: string; leaves: string[] } {
  const mid = HEIGHT / 2 + 4;
  const amp = 6;
  let stem = `M 4 ${mid}`;
  const seg = (width - 8) / 8;
  for (let i = 0; i < 8; i++) {
    const x0 = 4 + i * seg;
    stem += ` Q ${x0 + seg / 2} ${i % 2 === 0 ? mid - amp : mid + amp} ${x0 + seg} ${mid}`;
  }
  const leaves: string[] = [];
  for (let s = 1; s <= steps; s++) {
    const x = 4 + ((width - 8) * s) / steps - 10;
    const up = s % 2 === 1;
    const tipY = up ? 4 : HEIGHT - 2;
    leaves.push(
      `M ${x} ${mid} Q ${x - 10} ${(mid + tipY) / 2} ${x + 2} ${tipY} Q ${x + 12} ${(mid + tipY) / 2} ${x} ${mid} Z`
    );
  }
  return { stem, leaves };
}

export function VineProgress({ step, total }: { step: number; total: number }) {
  const [width, setWidth] = useState(0);
  const grow = useRef(new Animated.Value(Math.max(0, step - 1) / total)).current;

  useEffect(() => {
    if (width === 0) return;
    AccessibilityInfo.isReduceMotionEnabled()
      .catch(() => false)
      .then((still) => {
        if (still) grow.setValue(step / total);
        else Animated.spring(grow, { toValue: step / total, useNativeDriver: false, speed: 6, bounciness: 4 }).start();
      });
  }, [step, total, width, grow]);

  const { stem, leaves } = width ? vinePath(width, total) : { stem: "", leaves: [] };
  const clipWidth = grow.interpolate({ inputRange: [0, 1], outputRange: [0, width] });

  return (
    <View
      style={{ height: HEIGHT }}
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: total, now: step }}
    >
      {width > 0 && (
        <>
          <Svg width={width} height={HEIGHT} style={{ position: "absolute" }}>
            <Path d={stem} stroke={colors.border} strokeWidth={2} fill="none" strokeLinecap="round" />
            {leaves.map((d, i) => (
              <Path key={i} d={d} fill="none" stroke={colors.border} strokeWidth={1.5} />
            ))}
          </Svg>
          <Animated.View style={{ position: "absolute", height: HEIGHT, width: clipWidth, overflow: "hidden" }}>
            <Svg width={width} height={HEIGHT}>
              <Path d={stem} stroke={colors.brandGreen} strokeWidth={2.5} fill="none" strokeLinecap="round" />
              {leaves.map((d, i) => (
                <Path key={i} d={d} fill={i < step ? colors.brandGreen : "none"} stroke={colors.brandGreen} strokeWidth={1.5} />
              ))}
            </Svg>
          </Animated.View>
        </>
      )}
    </View>
  );
}
