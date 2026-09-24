import * as Location from "expo-location";
import { Barometer } from "expo-sensors";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../../src/api/client";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import { ScreenContainer, ScreenFooter } from "../../src/components/ScreenContainer";
import { TierBanner } from "../../src/components/TierBanner";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

type LanguagePref = "ms" | "iba" | "en";

const LANGUAGES: { value: LanguagePref; label: string }[] = [
  { value: "ms", label: "Bahasa Malaysia" },
  { value: "iba", label: "Jaku Iban" },
  { value: "en", label: "English" },
];

/**
 * §9.9 -- Registration & Location. GPS permission -> locate -> the backend
 * binds the nearest weather station on farm creation (§9.9's own data
 * dictionary: weather_station_id comes from the POST /farms response, never
 * asked of the farmer). Barometer DETECTION is silent and automatic
 * (docs/PROJECT_SPEC.md §4) -- the RESULT is shown via TierBanner, restored
 * 2026-09-18 after being wrongly dropped (docs/VALIDATION_CHECKLIST.md log).
 */
export default function RegisterScreen() {
  const setUser = useSessionStore((s) => s.setUser);
  const setFarm = useSessionStore((s) => s.setFarm);

  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [district, setDistrict] = useState("");
  const [farmName, setFarmName] = useState("");
  const [language, setLanguage] = useState<LanguagePref>("ms");
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [tierStatus, setTierStatus] = useState<"detecting" | "available" | "unavailable">("detecting");

  async function probeBarometer() {
    setTierStatus("detecting");
    const available = await Barometer.isAvailableAsync().catch(() => false);
    setTierStatus(available ? "available" : "unavailable");
  }

  useEffect(() => {
    probeBarometer();
  }, []);

  const canSubmit =
    displayName.trim().length > 0 &&
    district.trim().length > 0 &&
    farmName.trim().length > 0 &&
    coords !== null &&
    !submitting;

  async function handleLocate() {
    setError(null);
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        setError("GPS permission is needed to place your farm on the map.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      setCoords({ lat: position.coords.latitude, lon: position.coords.longitude });
    } catch {
      setError("Could not get your location. Try again outdoors, away from walls.");
    } finally {
      setLocating(false);
    }
  }

  async function handleSubmit() {
    if (!coords) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data: user, error: userError } = await api.POST("/users", {
        body: {
          display_name: displayName.trim(),
          phone: phone.trim() || null,
          district: district.trim(),
          language_pref: language,
        },
      });
      if (userError || !user) throw new Error("Could not register");
      setUser(user);

      // Reuses the same silent probe result TierBanner is already showing,
      // rather than probing a second time.
      const barometerAvailable = tierStatus === "available";

      // user.user_id!: ULID fields carry a Pydantic default_factory, so
      // openapi-typescript marks them optional even though a persisted row
      // always has one set (see app/schemas/common.py ulid_field()).
      const { data: farm, error: farmError } = await api.POST("/farms", {
        body: {
          user_id: user.user_id!,
          name: farmName.trim(),
          centroid_lat: coords.lat,
          centroid_lon: coords.lon,
          barometer_available: barometerAvailable,
        },
      });
      if (farmError || !farm) throw new Error("Could not create farm");
      setFarm(farm);

      router.replace("/(setup)/walk");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScreenContainer setupStep={1}>
      <Text style={styles.title}>Selamat datang ke PepperDex</Text>
      <Text style={styles.subtitle}>Let's set up your farm.</Text>

      <TierBanner status={tierStatus} onRetry={probeBarometer} />

      <View style={styles.field}>
        <Text style={styles.label}>Your name</Text>
        <TextInput
          value={displayName}
          onChangeText={setDisplayName}
          style={styles.input}
          placeholder="Nama anda"
          autoCapitalize="words"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Phone (optional)</Text>
        <TextInput
          value={phone}
          onChangeText={setPhone}
          style={styles.input}
          placeholder="+60"
          keyboardType="phone-pad"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>District</Text>
        <TextInput
          value={district}
          onChangeText={setDistrict}
          style={styles.input}
          placeholder="e.g. Julau"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Farm name</Text>
        <TextInput
          value={farmName}
          onChangeText={setFarmName}
          style={styles.input}
          placeholder="e.g. Kebun Lada Bapak"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Language</Text>
        <View style={styles.row}>
          {LANGUAGES.map((l) => (
            <Pressable
              key={l.value}
              onPress={() => setLanguage(l.value)}
              style={[styles.chip, language === l.value && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, language === l.value && styles.chipLabelActive]}>
                {l.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Farm location</Text>
        {coords ? (
          <Text style={styles.locatedText}>
            📍 Located ({coords.lat.toFixed(5)}, {coords.lon.toFixed(5)})
          </Text>
        ) : (
          <PrimaryButton label="Locate my farm" onPress={handleLocate} loading={locating} variant="secondary" />
        )}
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      <ScreenFooter>
        <PrimaryButton label="Continue" onPress={handleSubmit} disabled={!canSubmit} loading={submitting} />
      </ScreenFooter>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  title: { fontFamily: fonts.displayBold, fontSize: 24, color: colors.brandDark },
  subtitle: { fontFamily: fonts.body, fontSize: 15, color: colors.textMuted, marginBottom: spacing.md },
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
  locatedText: { fontFamily: fonts.body, fontSize: 15, color: colors.brandDark },
  error: { fontFamily: fonts.body, color: colors.danger, fontSize: 14 },
});
