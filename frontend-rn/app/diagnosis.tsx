import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../src/api/client";
import { uploadMedia } from "../src/api/media";
import { PrimaryButton } from "../src/components/PrimaryButton";
import { ScreenContainer, ScreenFooter } from "../src/components/ScreenContainer";
import { useSessionStore } from "../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../src/constants/theme";

type Target = "leaf" | "collar";
type Phase = "starting" | "pick" | "camera" | "uploading" | "result" | "analysing" | "analyse_failed" | "error";

interface CycleState {
  cycle_id: string;
  blocks_total: number;
  blocks_captured: number;
  status: string;
}

interface ObservationResponse {
  observation_id: string;
  cycle: CycleState | null;
  diagnosis: {
    predicted_class: string;
    confidence: number;
    below_threshold: boolean;
    mismatch_flag: string | null;
  };
  counts_as_check: boolean;
  retake_prompt: string | null;
  attempt: number;
  retakes_remaining: number;
  accepted_despite_mismatch: boolean;
}

interface BlockResult {
  label: string;
  rank: number;
  predicted_class: string;
  confidence: number;
}

const CLASS_LABEL: Record<string, string> = {
  healthy_leaf: "Healthy leaf",
  healthy_collar: "Healthy collar",
  foliar_yellowing: "Yellowing leaves",
  collar_lesion: "Collar lesion",
  defoliation_wilt: "Defoliation / wilt",
  unrelated: "Not a plant subject",
};

/**
 * §9.8 -- Diagnosis Capture Flow. Reached from the Advisor's "Begin Diagnosis"
 * button (§9.5) -- never straight from a block screen, so the Advisor gate
 * (§6's routing rule) can't be bypassed.
 *
 * Runs the backend's cycle (POST /farms/{id}/diagnosis-cycles resumes an
 * in-progress one), one block at a time: pick leaf/collar -> photo -> upload
 * -> POST /observations. A mismatched photo prompts a retake, the farmer can
 * always override ("use anyway" = force_accept) and after MAX_RETAKES the
 * backend accepts it anyway (pepperdex-rules §3 / §9). When every block is
 * captured the cycle completes and POST /agent/run arbitrates ONE
 * recommendation per block -- which is what fills the Home priority card.
 *
 * Known limits (see docs/PLAN.md): a resumed cycle does not tell the client
 * WHICH blocks are already counted, only how many, so resume assumes they
 * were the first N by elevation rank (the order this screen visits them).
 */
export default function DiagnosisScreen() {
  const farm = useSessionStore((s) => s.farm);
  const user = useSessionStore((s) => s.user);
  const queryClient = useQueryClient();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [phase, setPhase] = useState<Phase>("starting");
  const [error, setError] = useState<string | null>(null);
  const [cycle, setCycle] = useState<CycleState | null>(null);
  const [doneIds, setDoneIds] = useState<string[]>([]);
  const [results, setResults] = useState<Record<string, BlockResult>>({});
  const [target, setTarget] = useState<Target>("collar");
  const [last, setLast] = useState<ObservationResponse | null>(null);
  const [lastUpload, setLastUpload] = useState<{ uri: string; sha256: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", farm?.farm_id],
    queryFn: async () => {
      const { data, error: err } = await api.GET("/farms/{farm_id}/dashboard", {
        params: { path: { farm_id: farm!.farm_id! } },
      });
      if (err) throw err;
      return data;
    },
    enabled: !!farm,
  });

  const blocks = [...(dashboardQuery.data?.blocks ?? [])]
    .filter((b) => !b.is_external)
    .sort((a, b) => a.elevation_rank - b.elevation_rank);
  const current = blocks.find((b) => !doneIds.includes(b.block_id!));

  // Start (or resume) the cycle once the block list is known.
  useEffect(() => {
    if (!farm || blocks.length === 0 || cycle) return;
    (async () => {
      const { data, error: err } = await api.POST("/farms/{farm_id}/diagnosis-cycles", {
        params: { path: { farm_id: farm.farm_id! } },
        body: { trigger_reason: "user_initiated" },
      });
      if (err || !data) {
        setError("Could not start a diagnosis cycle. Check your connection and try again.");
        setPhase("error");
        return;
      }
      setCycle({
        cycle_id: data.cycle_id!,
        blocks_total: data.blocks_total,
        blocks_captured: data.blocks_captured ?? 0,
        status: data.status ?? "in_progress",
      });
      const resumed = data.blocks_captured ?? 0;
      if (resumed > 0) setDoneIds(blocks.slice(0, resumed).map((b) => b.block_id!));
      setPhase("pick");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farm?.farm_id, blocks.length]);

  async function openCamera() {
    setError(null);
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        setError("Camera permission is needed to photograph a block.");
        return;
      }
    }
    setPhase("camera");
  }

  async function submitObservation(upload: { uri: string; sha256: string }, forceAccept: boolean) {
    if (!cycle || !current || !user) return;
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST("/observations", {
        body: {
          cycle_id: cycle.cycle_id,
          block_id: current.block_id!,
          user_id: user.user_id!,
          image_uri: upload.uri,
          image_hash: upload.sha256,
          capture_target: target,
          captured_at: new Date().toISOString(),
          force_accept: forceAccept,
        },
      });
      if (err || !data) throw new Error("The photo could not be assessed.");
      const res = data as unknown as ObservationResponse;
      setLast(res);
      if (res.cycle) setCycle(res.cycle);
      if (res.counts_as_check) {
        setDoneIds((ids) => (ids.includes(current.block_id!) ? ids : [...ids, current.block_id!]));
        setResults((r) => ({
          ...r,
          [current.block_id!]: {
            label: current.label,
            rank: current.elevation_rank,
            predicted_class: res.diagnosis.predicted_class,
            confidence: res.diagnosis.confidence,
          },
        }));
      }
      setPhase("result");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
      setPhase("pick");
    } finally {
      setBusy(false);
    }
  }

  async function handleShutter() {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
      if (!photo?.uri) return;
      setPhase("uploading");
      const upload = await uploadMedia(photo.uri, "image/jpeg");
      setLastUpload({ uri: upload.uri, sha256: upload.sha256 });
      await submitObservation({ uri: upload.uri, sha256: upload.sha256 }, false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not take or upload the photo.");
      setPhase("pick");
    }
  }

  async function runAnalysis() {
    if (!farm || !cycle) return;
    setPhase("analysing");
    setError(null);
    const lines = Object.entries(results).map(
      ([blockId, r]) =>
        `- Block ${blockId} ("${r.label}", elevation_rank ${r.rank}): ${r.predicted_class}, confidence ${r.confidence.toFixed(2)}`
    );
    const message =
      `Diagnosis cycle ${cycle.cycle_id} is complete for farm_id ${farm.farm_id}. Results per block:\n` +
      `${lines.join("\n")}\n` +
      "Run the standard sequence: check the weather, project spread from the most severely diagnosed block, " +
      "look up treatment, find a spray window, and arbitrate one recommendation per affected block. " +
      `This farm's elevation_tier is '${farm.elevation_tier}'.`;
    try {
      // Background run: the agents' work streams into the Advisor chat
      // (GET /agent/runs/{id}/events) instead of the farmer watching a spinner
      // here for minutes. The chat refreshes Home when the run finishes.
      const { data, error: err } = await api.POST("/agent/run", {
        body: { farm_id: farm.farm_id!, message, cycle_id: cycle.cycle_id, trigger: "manual", background: true },
      });
      if (err || !data?.run_id) throw new Error("analysis failed");
      await queryClient.invalidateQueries({ queryKey: ["dashboard", farm.farm_id] });
      router.replace({ pathname: "/(tabs)/advisor", params: { runId: data.run_id } });
    } catch {
      setPhase("analyse_failed");
    }
  }

  // --- render ---------------------------------------------------------------

  if (phase === "camera") {
    return (
      <View style={styles.cameraContainer}>
        <CameraView ref={cameraRef} style={styles.camera} facing="back" />
        <View style={styles.cameraHint}>
          <Text style={styles.cameraHintText}>
            {target === "collar" ? "Aim at the stem base (collar)" : "Aim at a single leaf"}
          </Text>
        </View>
        <View style={styles.cameraControls}>
          <Pressable style={styles.shutter} onPress={handleShutter} />
        </View>
      </View>
    );
  }

  if (phase === "starting" || phase === "uploading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.brandGreen} />
        <Text style={styles.sub}>{phase === "uploading" ? "Assessing the photo…" : "Getting ready…"}</Text>
        {error && <Text style={styles.error}>{error}</Text>}
      </View>
    );
  }

  if (phase === "error") {
    return (
      <ScreenContainer>
        <Text style={styles.title}>Couldn't start</Text>
        <Text style={styles.error}>{error}</Text>
        <ScreenFooter>
          <PrimaryButton label="Back" onPress={() => router.back()} variant="secondary" />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  if (phase === "analysing") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.brandGreen} />
        <Text style={styles.title}>Working out what to do first…</Text>
        <Text style={styles.sub}>
          Checking the weather, projecting the spread and looking up the approved treatment. On the
          local model this can take a few minutes — please keep the app open.
        </Text>
      </View>
    );
  }

  if (phase === "analyse_failed") {
    return (
      <ScreenContainer>
        <Text style={styles.title}>Analysis is taking longer than expected</Text>
        <Text style={styles.sub}>
          Your photos are saved. The analysis may still finish in the background — check Home in a
          minute, or try again.
        </Text>
        <ScreenFooter>
          <PrimaryButton label="Try again" onPress={runAnalysis} />
          <PrimaryButton label="Go to Home" onPress={() => router.replace("/(tabs)")} variant="secondary" />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  const allDone = !!cycle && (cycle.status === "complete" || !current);
  const position = cycle ? Math.min(cycle.blocks_captured + 1, cycle.blocks_total) : 1;

  if (phase === "result" && last) {
    const d = last.diagnosis;
    const needsRetake = !last.counts_as_check;
    return (
      <ScreenContainer>
        <Text style={styles.title}>{CLASS_LABEL[d.predicted_class] ?? d.predicted_class}</Text>
        <Text style={styles.sub}>Confidence {(d.confidence * 100).toFixed(0)}%</Text>
        {d.below_threshold && (
          <Text style={styles.warn}>Keyakinan rendah — periksa sendiri. This is a prompt to look, not a diagnosis.</Text>
        )}
        {needsRetake && last.retake_prompt && <Text style={styles.warn}>{last.retake_prompt}</Text>}
        {last.accepted_despite_mismatch && (
          <Text style={styles.sub}>Accepted as-is — you have photographed this block enough times.</Text>
        )}
        {error && <Text style={styles.error}>{error}</Text>}

        <ScreenFooter>
          {needsRetake ? (
            <>
              <PrimaryButton label="Retake photo" onPress={openCamera} />
              <PrimaryButton
                label="Use this photo anyway"
                onPress={() => lastUpload && submitObservation(lastUpload, true)}
                loading={busy}
                variant="secondary"
              />
            </>
          ) : allDone ? (
            <PrimaryButton label="Finish and get my priority action" onPress={runAnalysis} />
          ) : (
            <PrimaryButton label="Next block" onPress={() => setPhase("pick")} />
          )}
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  // phase === "pick"
  if (allDone) {
    return (
      <ScreenContainer>
        <Text style={styles.title}>All blocks photographed</Text>
        <ScreenFooter>
          <PrimaryButton label="Finish and get my priority action" onPress={runAnalysis} />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer>
      <Text style={styles.progress}>
        Block {position} of {cycle?.blocks_total ?? blocks.length}
      </Text>
      <Text style={styles.title}>{current?.label ?? "…"}</Text>
      <Text style={styles.sub}>What are you going to photograph?</Text>
      <View style={styles.row}>
        {(["collar", "leaf"] as Target[]).map((t) => (
          <Pressable
            key={t}
            onPress={() => setTarget(t)}
            style={[styles.chip, target === t && styles.chipActive]}
          >
            <Text style={[styles.chipLabel, target === t && styles.chipLabelActive]}>
              {t === "collar" ? "Stem base (collar)" : "Leaf"}
            </Text>
          </Pressable>
        ))}
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
      <ScreenFooter>
        <PrimaryButton label="Open camera" onPress={openCamera} disabled={!current} />
      </ScreenFooter>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.brandDark },
  progress: { fontFamily: fonts.mono, fontSize: 12, color: colors.textMuted, textTransform: "uppercase" },
  sub: { fontFamily: fonts.body, fontSize: 15, color: colors.textMuted },
  warn: { fontFamily: fonts.body, fontSize: 14, color: colors.warning },
  error: { fontFamily: fonts.body, fontSize: 14, color: colors.danger },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.brandGreen, borderColor: colors.brandGreen },
  chipLabel: { fontFamily: fonts.body, color: colors.text, fontSize: 14 },
  chipLabelActive: { color: "#fff", fontFamily: fonts.bodySemi },
  cameraContainer: { flex: 1, backgroundColor: "#000" },
  camera: { flex: 1 },
  cameraHint: { position: "absolute", top: spacing.lg, left: 0, right: 0, alignItems: "center" },
  cameraHintText: {
    fontFamily: fonts.body,
    color: "#fff",
    backgroundColor: "rgba(0,0,0,0.5)",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.lg,
    fontSize: 13,
  },
  cameraControls: { position: "absolute", bottom: spacing.xl, left: 0, right: 0, alignItems: "center" },
  shutter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: "#fff",
    borderWidth: 4,
    borderColor: colors.border,
  },
});
