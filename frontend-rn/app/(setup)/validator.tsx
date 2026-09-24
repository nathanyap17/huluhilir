import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { api } from "../../src/api/client";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import { ScreenFooter } from "../../src/components/ScreenContainer";
import { SafeTerrainScene as TerrainScene } from "../../src/components/SafeTerrainScene";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, spacing } from "../../src/constants/theme";
import { StartOverLink } from "../../src/components/StartOverLink";
import { VineProgress } from "../../src/components/VineProgress";

/**
 * §9.13 -- Validator Summary. `farm_graph_preview` reuses §9.6's 3D terrain
 * canvas (docs/PROJECT_SPEC.md §9.13) -- now real (Phase C:
 * frontend-rn/src/components/TerrainScene.tsx), fed by the same
 * GET /farms/{farm_id}/dashboard response Farm tab uses (terrain_nodes/
 * terrain_edges), so the farmer's first look at their farm and the Farm
 * tab's later view are the same scene, not two different renderings of it.
 *
 * There is no dedicated `check_setup_state` endpoint in the real backend to
 * source `flagged_issues` from (PLAN.md's Phase A note: extend what
 * exists), so issues are derived here from data the dashboard already
 * returns, rather than invented.
 */
export default function ValidatorScreen() {
  const farm = useSessionStore((s) => s.farm);

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

  const blocks = dashboardQuery.data?.terrain_nodes ?? [];
  const edges = dashboardQuery.data?.terrain_edges ?? [];

  const flaggedIssues: string[] = [];
  if (blocks.length < 2) {
    flaggedIssues.push("Only one block captured — spread projection needs at least two to show a path.");
  }

  return (
    <View style={styles.flex}>
      <View style={styles.header}>
        <VineProgress step={4} total={4} />
        <StartOverLink />
        <Text style={styles.title}>Your farm, from high to low</Text>
        <Text style={styles.subtitle}>Water flows downhill through this order. Drag to rotate.</Text>
      </View>

      <View style={styles.sceneContainer}>
        <TerrainScene blocks={blocks} edges={edges} onSelectBlock={() => {}} />
      </View>

      {flaggedIssues.map((issue) => (
        <Text key={issue} style={styles.issue}>
          ⚠ {issue}
        </Text>
      ))}

      <ScreenFooter>
        <PrimaryButton label="Finish setup" onPress={() => router.replace("/(tabs)")} />
      </ScreenFooter>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  header: { padding: spacing.lg, gap: spacing.xs },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.brandDark },
  subtitle: { fontFamily: fonts.body, fontSize: 15, color: colors.textMuted },
  sceneContainer: { flex: 1 },
  issue: { fontFamily: fonts.body, color: colors.warning, fontSize: 14, paddingHorizontal: spacing.lg },
});
