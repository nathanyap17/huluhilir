import { useState } from "react";
import { View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../constants/theme";

/**
 * The Advisor's single organic flourish (MOCK_DESIGN.md §6): a leaf-vein line
 * dividing the conversation from the input -- a midrib with paired veins that
 * shorten toward the tip. Static and decorative (hidden from screen readers).
 */
export function LeafVein({ height = 16 }: { height?: number }) {
  const [width, setWidth] = useState(0);
  const mid = height / 2;
  let d = "";
  if (width > 0) {
    d = `M ${spacingX(width, 0)} ${mid} L ${spacingX(width, 1)} ${mid}`;
    const pairs = 9;
    for (let i = 1; i <= pairs; i++) {
      const x = spacingX(width, i / (pairs + 1));
      const reach = (height / 2 - 1) * (1 - i / (pairs + 2));
      const run = 14 + 10 * (1 - i / pairs);
      d += ` M ${x} ${mid} q ${run * 0.6} ${-reach * 0.2} ${run} ${-reach}`;
      d += ` M ${x} ${mid} q ${run * 0.6} ${reach * 0.2} ${run} ${reach}`;
    }
  }
  return (
    <View
      style={{ height, marginHorizontal: 20 }}
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      accessible={false}
      importantForAccessibility="no-hide-descendants"
    >
      {width > 0 && (
        <Svg width={width} height={height}>
          <Path d={d} stroke={colors.brandLight} strokeWidth={1.2} fill="none" strokeLinecap="round" />
        </Svg>
      )}
    </View>
  );
}

function spacingX(width: number, t: number): number {
  return 2 + t * (width - 4);
}
