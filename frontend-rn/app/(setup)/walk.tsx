import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import { AudioModule, RecordingPresets, useAudioRecorder } from "expo-audio";
import * as Location from "expo-location";
import { router } from "expo-router";
import { Barometer } from "expo-sensors";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../../src/api/client";
import { uploadMedia } from "../../src/api/media";
import { AltitudeReadout } from "../../src/components/AltitudeReadout";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import { ScreenContainer, ScreenFooter } from "../../src/components/ScreenContainer";
import { TierBanner } from "../../src/components/TierBanner";
import { SafeWalkMapView as WalkMapView } from "../../src/components/SafeWalkMapView";
import { useSessionStore } from "../../src/store/sessionStore";
import { relativeAltitudeM } from "../../src/utils/barometer";
import { haversineM } from "../../src/utils/geo";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

type Drainage = "good" | "fair" | "poor";
type Phase = "idle" | "marking" | "camera" | "details" | "submitting";

const SAMPLE_WINDOW_MS = 5000;
const SAMPLE_INTERVAL_MS = 500;

/**
 * §9.10 -- Block Capture Loop, plus what would have been §9.12's per-block
 * drainage tap. There is no PATCH /blocks/{id} in the real backend
 * (backend/app/routers/setup.py) -- `drainage` only exists as a field on
 * BlockCaptureRequest, set at capture time -- so drainage is asked here,
 * folded into one screen, rather than as a separate wizard step the API
 * has no way to persist afterwards.
 *
 * Note on the `!` non-null assertions on *_id fields below: every ID field
 * (farm_id, walk_session_id, block_id, ...) is declared with a Pydantic
 * `default_factory` (app/schemas/common.py ulid_field()), which makes
 * openapi-typescript mark it optional in the generated response type even
 * though a persisted row always has one. The assertions document that gap,
 * not a real possibility of undefined here.
 */
export default function WalkScreen() {
  const farm = useSessionStore((s) => s.farm);
  const queryClient = useQueryClient();
  const [permission, requestPermission] = useCameraPermissions();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const cameraRef = useRef<CameraView>(null);
  const cachedBaselineRef = useRef<number | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  // Median barometer reading at the block; the SERVER turns it into a height
  // against the walk's stored baseline (restart-safe; fixed 2026-09-27).
  const [pressureHpa, setPressureHpa] = useState<number | null>(null);
  const [positionSamples, setPositionSamples] = useState<[number, number][]>([]);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [voiceUri, setVoiceUri] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);

  const [label, setLabel] = useState("");
  const [drainage, setDrainage] = useState<Drainage>("fair");
  const [isExternal, setIsExternal] = useState(false);
  const [ownerName, setOwnerName] = useState("");
  const [ownerPhone, setOwnerPhone] = useState("");

  // Live map + position readout state -- restored 2026-09-18, see this
  // file's header comment and docs/VALIDATION_CHECKLIST.md's log. Separate
  // from `positionSamples` above: this is a continuous background watch
  // for the map/readout, not the burst ±5s sample used to derive a
  // block's actual centroid.
  const [track, setTrack] = useState<{ lat: number; lon: number }[]>([]);
  const [current, setCurrent] = useState<{ lat: number; lon: number; accuracy: number } | null>(null);
  const [liveAltitudeM, setLiveAltitudeM] = useState<number | null>(null);

  useEffect(() => {
    let locationSub: Location.LocationSubscription | null = null;
    let barometerSub: { remove: () => void } | null = null;

    (async () => {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") return;
      locationSub = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, timeInterval: 3000, distanceInterval: 3 },
        (pos) => {
          const point = { lat: pos.coords.latitude, lon: pos.coords.longitude };
          setCurrent({ ...point, accuracy: pos.coords.accuracy ?? 999 });
          setTrack((prev) => [...prev, point]);
        }
      );
    })();

    if (farm?.barometer_available) {
      readBarometerBaselineOnce()
        .then((baseline) => {
          barometerSub = Barometer.addListener(({ pressure }) => {
            setLiveAltitudeM(relativeAltitudeM(pressure, baseline));
          });
        })
        .catch(() => {
          // No baseline yet (walk session not started) -- the live readout
          // just stays blank until the first "Mark this block" establishes
          // one; it never blocks capture.
        });
    }

    return () => {
      locationSub?.remove();
      barometerSub?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farm?.barometer_available]);

  function readBarometerBaselineOnce(): Promise<number> {
    if (cachedBaselineRef.current !== null) return Promise.resolve(cachedBaselineRef.current);
    return readBarometerOnce();
  }

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", farm?.farm_id],
    queryFn: async () => {
      if (!farm) return null;
      const { data, error: err } = await api.GET("/farms/{farm_id}/dashboard", {
        params: { path: { farm_id: farm.farm_id! } },
      });
      if (err) throw err;
      return data;
    },
    enabled: !!farm,
  });

  const blocks = dashboardQuery.data?.blocks ?? [];

  async function ensureWalkSession(): Promise<string> {
    if (farm?.walk_session_id) return farm.walk_session_id;
    if (!farm) throw new Error("no farm in session");

    let baselineHpa: number | undefined;
    if (farm.barometer_available) {
      baselineHpa = await readBarometerOnce().catch(() => undefined);
      if (baselineHpa !== undefined) cachedBaselineRef.current = baselineHpa;
    }
    const { data, error: err } = await api.POST("/farms/{farm_id}/walk-sessions", {
      params: { path: { farm_id: farm.farm_id! }, query: { baseline_pressure_hpa: baselineHpa } },
    });
    if (err || !data) throw new Error("could not start walk session");
    useSessionStore.getState().setFarm({ ...farm, walk_session_id: data.walk_session_id });
    return data.walk_session_id!;
  }

  function readBarometerOnce(): Promise<number> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        sub.remove();
        reject(new Error("barometer timeout"));
      }, 3000);
      const sub = Barometer.addListener(({ pressure }) => {
        clearTimeout(timeout);
        sub.remove();
        resolve(pressure);
      });
    });
  }

  async function handleStartCapture() {
    setError(null);
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        setError("Camera permission is needed to photograph a block.");
        return;
      }
    }
    const locPerm = await Location.requestForegroundPermissionsAsync();
    if (locPerm.status !== "granted") {
      setError("Location permission is needed to place this block.");
      return;
    }

    setPhase("marking");
    const samples: [number, number][] = [];
    const start = Date.now();

    const walkSessionId = await ensureWalkSession().catch((e) => {
      setError(e instanceof Error ? e.message : "Could not start walk session");
      setPhase("idle");
      return null;
    });
    if (!walkSessionId) return;

    // Collect pressure for the whole capture window, not one instant: the
    // median of ~5 s of readings rejects sensor noise (~0.1 hPa ≈ 1 m).
    const pressures: number[] = [];
    const pressureSub = farm?.barometer_available
      ? Barometer.addListener(({ pressure }) => pressures.push(pressure))
      : null;

    while (Date.now() - start < SAMPLE_WINDOW_MS) {
      try {
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        samples.push([pos.coords.latitude, pos.coords.longitude]);
        api
          .POST("/walk-sessions/{walk_session_id}/samples", {
            params: { path: { walk_session_id: walkSessionId } },
            body: {
              samples: [
                {
                  walk_session_id: walkSessionId,
                  lat: pos.coords.latitude,
                  lon: pos.coords.longitude,
                  gps_alt_m: pos.coords.altitude ?? undefined,
                  gps_accuracy_m: pos.coords.accuracy ?? 999,
                  recorded_at: new Date().toISOString(),
                },
              ],
            },
          })
          .catch(() => {
            // Offline outbox is a Phase D concern; a dropped sample batch
            // here does not block capture -- the median centroid still
            // works off whatever samples DID arrive.
          });
      } catch {
        // one bad reading in the window is fine; median rejects jitter
      }
      await new Promise((r) => setTimeout(r, SAMPLE_INTERVAL_MS));
    }
    setPositionSamples(samples);

    pressureSub?.remove();
    if (pressures.length > 0) {
      const sorted = [...pressures].sort((a, b) => a - b);
      setPressureHpa(sorted[Math.floor(sorted.length / 2)]);
    }

    setPhase("camera");
  }


  // Barometer phones: when every block has a reading and no two are within
  // 2 m, the slope is already known -- finish the ranking here and skip the
  // "which is higher?" page. Otherwise (no barometer, missing readings, or
  // close pairs the sensor can't separate) the farmer answers as before.
  const [continuing, setContinuing] = useState(false);
  async function handleContinue() {
    if (!farm) return;
    if (!farm.barometer_available) {
      router.push("/(setup)/elevation");
      return;
    }
    setContinuing(true);
    setError(null);
    try {
      const { data } = await api.GET("/farms/{farm_id}/elevation-questions", {
        params: { path: { farm_id: farm.farm_id! } },
      });
      const q = data as unknown as { barometer_used?: boolean; questions?: unknown[] } | undefined;
      if (q?.barometer_used && (q.questions ?? []).length === 0) {
        const { error: err } = await api.POST("/farms/{farm_id}/resolve-elevation", {
          params: { path: { farm_id: farm.farm_id! } },
          body: { answers: [] },
        });
        if (err) throw new Error("Could not work out the slope");
        useSessionStore.getState().setFarm({ ...farm, setup_completed_at: new Date().toISOString() });
        router.replace("/(setup)/validator");
        return;
      }
      router.push("/(setup)/elevation");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setContinuing(false);
    }
  }

  async function handleTakePhoto() {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
      if (photo?.uri) {
        setPhotoUri(photo.uri);
        setPhase("details");
      }
    } catch {
      setError("Could not take photo. Try again.");
    }
  }

  async function handleToggleRecording() {
    if (isRecording) {
      await recorder.stop();
      setVoiceUri(recorder.uri ?? null);
      setIsRecording(false);
      return;
    }
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) return;
    await recorder.prepareToRecordAsync();
    recorder.record();
    setIsRecording(true);
  }

  function resetCapture() {
    setPhase("idle");
    setPhotoUri(null);
    setVoiceUri(null);
    setLabel("");
    setDrainage("fair");
    setIsExternal(false);
    setOwnerName("");
    setOwnerPhone("");
    setPressureHpa(null);
    setPositionSamples([]);
  }

  async function handleConfirmBlock() {
    if (!farm || !photoUri || positionSamples.length === 0) return;
    setPhase("submitting");
    setError(null);
    try {
      const photoUpload = await uploadMedia(photoUri, "image/jpeg");
      let voiceLabelUri: string | undefined;
      if (voiceUri) {
        const voiceUpload = await uploadMedia(voiceUri, "audio/mp4");
        voiceLabelUri = voiceUpload.uri;
      }

      const { error: err } = await api.POST("/farms/{farm_id}/blocks", {
        params: { path: { farm_id: farm.farm_id! } },
        body: {
          label: label.trim() || `Blok ${blocks.length + 1}`,
          photo_uri: photoUpload.uri,
          voice_label_uri: voiceLabelUri,
          position_samples: positionSamples,
          pressure_hpa: pressureHpa ?? undefined,
          drainage,
          is_external: isExternal,
          external_owner_name: isExternal ? ownerName.trim() || undefined : undefined,
          external_owner_phone: isExternal ? ownerPhone.trim() || undefined : undefined,
        },
      });
      if (err) throw new Error("Could not save block");

      await queryClient.invalidateQueries({ queryKey: ["dashboard", farm.farm_id] });
      resetCapture();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this block. Try again.");
      setPhase("details");
    }
  }

  if (phase === "camera") {
    return (
      <View style={styles.cameraContainer}>
        <CameraView ref={cameraRef} style={styles.camera} facing="back" />
        <View style={styles.cameraControls}>
          <Pressable style={styles.shutter} onPress={handleTakePhoto} />
        </View>
      </View>
    );
  }

  if (phase === "details") {
    return (
      <ScreenContainer setupStep={2}>
        {photoUri && <Image source={{ uri: photoUri }} style={styles.preview} />}

        <View style={styles.field}>
          <Text style={styles.label}>Block name (optional)</Text>
          <TextInput
            value={label}
            onChangeText={setLabel}
            style={styles.input}
            placeholder="e.g. Kebun Tua"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Voice label (optional) — recorded, never transcribed</Text>
          <PrimaryButton
            label={isRecording ? "Stop recording" : voiceUri ? "Re-record" : "Record voice label"}
            onPress={handleToggleRecording}
            variant={isRecording ? "danger" : "secondary"}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Drainage</Text>
          <View style={styles.row}>
            {(["good", "fair", "poor"] as Drainage[]).map((d) => (
              <Pressable
                key={d}
                onPress={() => setDrainage(d)}
                style={[styles.chip, drainage === d && styles.chipActive]}
              >
                <Text style={[styles.chipLabel, drainage === d && styles.chipLabelActive]}>{d}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={styles.field}>
          <Pressable style={styles.row} onPress={() => setIsExternal((v) => !v)}>
            <View style={[styles.checkbox, isExternal && styles.checkboxChecked]} />
            <Text style={styles.label}>This is a neighbour's block (not mine)</Text>
          </Pressable>
        </View>

        {isExternal && (
          <>
            <View style={styles.field}>
              <Text style={styles.label}>Neighbour's name</Text>
              <TextInput value={ownerName} onChangeText={setOwnerName} style={styles.input} />
            </View>
            <View style={styles.field}>
              <Text style={styles.label}>Neighbour's phone</Text>
              <TextInput
                value={ownerPhone}
                onChangeText={setOwnerPhone}
                style={styles.input}
                keyboardType="phone-pad"
              />
            </View>
          </>
        )}

        {error && <Text style={styles.error}>{error}</Text>}

        <ScreenFooter>
          <PrimaryButton label="Save block" onPress={handleConfirmBlock} />
          <PrimaryButton label="Discard" onPress={resetCapture} variant="secondary" />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  const lastMark = blocks[blocks.length - 1];
  const distanceToLastMarkM =
    current && lastMark ? haversineM(current.lat, current.lon, lastMark.centroid_lat, lastMark.centroid_lon) : null;

  return (
    <ScreenContainer setupStep={2}>
      <Text style={styles.title}>Walk your farm</Text>
      <Text style={styles.subtitle}>
        Stand at each block and tap "Mark this block". Do this for every block, from any point
        first — order does not matter.
      </Text>

      <TierBanner status={farm?.barometer_available ? "available" : "unavailable"} blockCount={blocks.length} />

      <WalkMapView
        track={track}
        current={current}
        blocks={blocks.map((b) => ({
          block_id: b.block_id!,
          label: b.label,
          lat: b.centroid_lat,
          lon: b.centroid_lon,
          rank: b.elevation_rank,
        }))}
      />

      <View style={styles.positionRow}>
        <View style={styles.positionCol}>
          <Text style={styles.positionLabel}>Position</Text>
          <Text style={styles.positionValue}>
            {current ? `${current.lat.toFixed(5)}, ${current.lon.toFixed(5)}` : "Locating…"}
          </Text>
          {current && <Text style={styles.positionSub}>±{current.accuracy.toFixed(0)}m accuracy</Text>}
        </View>
        {distanceToLastMarkM != null && (
          <View style={styles.positionCol}>
            <Text style={styles.positionLabel}>From last mark</Text>
            <Text style={styles.positionValue}>{distanceToLastMarkM.toFixed(0)}m</Text>
          </View>
        )}
        {farm?.barometer_available && <AltitudeReadout relativeM={liveAltitudeM} />}
      </View>

      {blocks.length > 0 && (
        <View style={styles.field}>
          <Text style={styles.label}>Blocks captured: {blocks.length}</Text>
          {blocks.map((b) => (
            <Text key={b.block_id} style={styles.blockRow}>
              • {b.label}
            </Text>
          ))}
        </View>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      {phase === "marking" ? (
        <View style={styles.markingBox}>
          <ActivityIndicator size="large" color={colors.brandGreen} />
          <Text style={styles.subtitle}>Hold still, marking position…</Text>
        </View>
      ) : (
        <PrimaryButton label="Mark this block" onPress={handleStartCapture} />
      )}

      <ScreenFooter>
        <PrimaryButton
          label={
            farm?.barometer_available
              ? `Continue (${blocks.length} block${blocks.length === 1 ? "" : "s"})`
              : `Continue to elevation (${blocks.length} block${blocks.length === 1 ? "" : "s"})`
          }
          onPress={handleContinue}
          loading={continuing}
          disabled={blocks.length < 1 || phase === "marking" || continuing}
          variant="secondary"
        />
      </ScreenFooter>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.brandDark },
  subtitle: { fontFamily: fonts.body, fontSize: 15, color: colors.textMuted },
  field: { gap: spacing.xs },
  label: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.text },
  input: {
    fontFamily: fonts.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    fontSize: 16,
    backgroundColor: colors.surface,
  },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
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
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  checkboxChecked: { backgroundColor: colors.brandGreen, borderColor: colors.brandGreen },
  error: { fontFamily: fonts.body, color: colors.danger, fontSize: 14 },
  blockRow: { fontFamily: fonts.body, fontSize: 14, color: colors.text, paddingVertical: 2 },
  positionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.lg,
    padding: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  positionCol: { gap: 2 },
  positionLabel: { fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted, textTransform: "uppercase" },
  positionValue: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.text },
  positionSub: { fontFamily: fonts.body, fontSize: 10, color: colors.textMuted },
  markingBox: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.lg },
  cameraContainer: { flex: 1, backgroundColor: "#000" },
  camera: { flex: 1 },
  cameraControls: {
    position: "absolute",
    bottom: spacing.xl,
    left: 0,
    right: 0,
    alignItems: "center",
  },
  shutter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: "#fff",
    borderWidth: 4,
    borderColor: colors.border,
  },
  preview: { width: "100%", height: 220, borderRadius: radius.md, backgroundColor: colors.surface },
});
