import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { api } from "../../src/api/client";
import { SafeTerrainScene as TerrainScene } from "../../src/components/SafeTerrainScene";
import { useT, type StringKey } from "../../src/i18n";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

const LEGEND: { state: string; color: string }[] = [
  { state: "protected", color: colors.stateProtected },
  { state: "alerted", color: colors.stateAlerted },
  { state: "harmed", color: colors.stateHarmed },
  { state: "overrun", color: colors.stateOverrun },
];

/**
 * §9.6 -- Terrain Risk Canvas, the real 3D scene
 * (frontend-rn/src/components/TerrainScene.tsx, @react-three/fiber +
 * expo-gl). Backend supplies x_rot_m/y_rot_m (app/tools/terrain.py,
 * computed at response time, never persisted); this screen owns camera,
 * z_height, and scene_scale entirely client-side, per §9.6's data
 * dictionary. Drag anywhere on the canvas to orbit.
 */
export default function FarmScreen() {
  const farm = useSessionStore((s) => s.farm);
  const { t } = useT();

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", farm?.farm_id],
    queryFn: async () => {
      const { data, error } = await api.GET("/farms/{farm_id}/dashboard", {
        params: { path: { farm_id: farm!.farm_id! } },
      });
      if (error) throw error;
      return data;
    },
    enabled: !!farm,
  });

  if (dashboardQuery.isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const blocks = dashboardQuery.data?.terrain_nodes ?? [];
  const edges = dashboardQuery.data?.terrain_edges ?? [];

  if (blocks.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>{t("no_blocks")}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <TerrainScene
        blocks={blocks}
        edges={edges}
        onSelectBlock={(blockId) => router.push(`/farm/${blockId}`)}
      />
      <View style={styles.legend}>
        {LEGEND.map((item) => (
          <View key={item.state} style={styles.legendRow}>
            <View style={[styles.legendDot, { backgroundColor: item.color }]} />
            <Text style={styles.legendLabel}>{t(`legend_${item.state}` as StringKey)}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.hint}>{t("farm_hint")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 14 },
  legend: {
    position: "absolute",
    top: spacing.md,
    left: spacing.md,
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: radius.md,
    padding: spacing.sm,
    gap: 4,
  },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendLabel: { fontFamily: fonts.body, fontSize: 12, color: colors.text },
  hint: {
    fontFamily: fonts.body,
    position: "absolute",
    bottom: spacing.md,
    alignSelf: "center",
    fontSize: 12,
    color: colors.textMuted,
  },
});
