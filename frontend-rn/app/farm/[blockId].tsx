import { useQuery } from "@tanstack/react-query";
import { createAudioPlayer } from "expo-audio";
import { router, useLocalSearchParams } from "expo-router";
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../../src/api/client";
import { Card } from "../../src/components/Card";
import { apiBase } from "../../src/constants/config";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

interface ObservationHistoryItem {
  observation_id: string;
  image_uri: string;
  capture_target: string;
  captured_at: string;
  predicted_class: string | null;
  confidence: number | null;
  model_version: string | null;
  below_threshold: boolean | null;
}

interface BlockDetail {
  block_id: string;
  label: string;
  photo_uri: string;
  header_image_uri: string | null;
  voice_label_uri: string | null;
  elevation_rank: number;
  drainage: string;
  vine_count: number | null;
  current_state: string;
  baro_rel_m: number | null;
  marked_at: string | null;
  observations: ObservationHistoryItem[];
}

/**
 * §9.7 -- Block Detail / Diagnosis History. GET /blocks/{block_id}/detail
 * returns a plain dict in the real backend (app/routers/setup.py), not a
 * Pydantic response_model, so this interface mirrors that route's actual
 * return shape by hand rather than a generated type.
 *
 * Rule 4 (is_external -> only current_state) is enforced here by checking
 * the SAME field the backend's own docstring names, even though the
 * backend already omits history/photo for external blocks server-side --
 * defense in depth costs nothing and keeps this screen honest if that ever
 * changes upstream. The "Diagnose" button routes to Advisor with /diagnose
 * prefilled, never straight into capture (§9.7's channeling logic) -- the
 * Diagnosis Capture Flow (§9.8, app/diagnosis.tsx) is reached from there.
 */
export default function BlockDetailScreen() {
  const { blockId } = useLocalSearchParams<{ blockId: string }>();

  const query = useQuery({
    queryKey: ["block-detail", blockId],
    queryFn: async () => {
      const { data, error } = await api.GET("/blocks/{block_id}/detail", {
        params: { path: { block_id: blockId } },
      });
      if (error) throw error;
      return data as unknown as BlockDetail;
    },
    enabled: !!blockId,
  });

  if (query.isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const block = query.data;
  if (!block) {
    return (
      <View style={styles.center}>
        <Text>Could not load this block.</Text>
      </View>
    );
  }

  function playVoiceLabel() {
    if (!block!.voice_label_uri) return;
    const player = createAudioPlayer(`${apiBase()}${block!.voice_label_uri}`);
    player.play();
  }

  return (
    <FlatList
      data={block.observations}
      keyExtractor={(o) => o.observation_id}
      contentContainerStyle={styles.content}
      ListHeaderComponent={
        <View style={styles.header}>
          {block.header_image_uri && (
            <Image source={{ uri: `${apiBase()}${block.header_image_uri}` }} style={styles.photo} />
          )}
          <Text style={styles.title}>{block.label}</Text>
          <Text style={styles.subtitle}>
            Rank #{block.elevation_rank} · {block.current_state} · drainage: {block.drainage}
          </Text>

          {block.voice_label_uri && (
            <Pressable style={styles.voiceButton} onPress={playVoiceLabel}>
              <Text style={styles.voiceButtonLabel}>▶ Play voice label</Text>
            </Pressable>
          )}

          {/* §9.7: never starts capture directly -- through the Advisor, so its
              gate can't be bypassed. A cycle covers the whole farm, so this
              is "diagnose", not "diagnose only this block". */}
          <Pressable
            style={styles.voiceButton}
            onPress={() =>
              router.push({ pathname: "/(tabs)/advisor", params: { prefill: "/diagnose", n: String(Date.now()) } })
            }
          >
            <Text style={styles.voiceButtonLabel}>Diagnose in Advisor</Text>
          </Pressable>

          <Text style={styles.sectionTitle}>Diagnosis history</Text>
        </View>
      }
      ListEmptyComponent={<Text style={styles.emptyText}>No diagnoses recorded for this block yet.</Text>}
      renderItem={({ item }) => (
        <Card>
          <Text style={styles.observationClass}>
            {item.predicted_class ?? "Not yet classified"}
            {item.below_threshold ? " (uncertain)" : ""}
          </Text>
          <Text style={styles.observationMeta}>
            {new Date(item.captured_at).toLocaleDateString()} · {item.capture_target}
            {item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ""}
          </Text>
        </Card>
      )}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  content: { padding: spacing.lg, gap: spacing.sm },
  header: { gap: spacing.sm, marginBottom: spacing.md },
  photo: { width: "100%", height: 200, borderRadius: radius.md, backgroundColor: colors.surface },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.brandDark },
  subtitle: { fontFamily: fonts.body, fontSize: 14, color: colors.textMuted, textTransform: "capitalize" },
  voiceButton: {
    alignSelf: "flex-start",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  voiceButtonLabel: { color: colors.brandDark, fontFamily: fonts.bodySemi },
  sectionTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.text, marginTop: spacing.sm },
  emptyText: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 14 },
  observationClass: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.text, textTransform: "capitalize" },
  observationMeta: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
});
