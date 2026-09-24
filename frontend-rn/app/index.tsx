import { useQuery } from "@tanstack/react-query";
import { Redirect } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { api } from "../src/api/client";
import { useSessionStore } from "../src/store/sessionStore";

/**
 * The hard gate (docs/PROJECT_SPEC.md §9.0): checked on every cold start.
 * A cached `farm.setup_completed_at` is only a fast first paint -- GET
 * /farms/{farm_id}'s own docstring warns against trusting a stale local
 * copy, so this always re-fetches from the server before deciding.
 */
export default function Gate() {
  const cachedFarm = useSessionStore((s) => s.farm);
  const setFarm = useSessionStore((s) => s.setFarm);

  const farmQuery = useQuery({
    queryKey: ["farm", cachedFarm?.farm_id],
    queryFn: async () => {
      if (!cachedFarm) return null;
      // farm_id!: ULID fields carry a Pydantic default_factory, so
      // openapi-typescript marks them optional even though a persisted row
      // always has one set (see app/schemas/common.py ulid_field()).
      const { data, error } = await api.GET("/farms/{farm_id}", {
        params: { path: { farm_id: cachedFarm.farm_id! } },
      });
      if (error) throw error;
      setFarm(data);
      return data;
    },
    enabled: !!cachedFarm,
  });

  if (!cachedFarm) {
    return <Redirect href="/(setup)/welcome" />;
  }

  if (farmQuery.isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  // Server unreachable on this cold start (e.g. laptop off hotspot). Fall
  // back to the cached copy rather than stranding the farmer on a spinner --
  // rule 6 requires the app to keep working, and the dashboard itself
  // tolerates a farm with no fresh data far better than showing nothing.
  const farm = farmQuery.data ?? cachedFarm;

  if (!farm.setup_completed_at) {
    return <Redirect href="/(setup)/walk" />;
  }

  return <Redirect href="/(tabs)" />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
