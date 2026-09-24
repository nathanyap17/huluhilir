import { router } from "expo-router";
import { useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../../src/api/client";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import { ServerAddressField } from "../../src/components/ServerAddressField";
import { apiBase } from "../../src/constants/config";
import { useT } from "../../src/i18n";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

const LOGO = require("../../assets/brand/pepperdex-wordmark.png");

/**
 * First launch on a phone with no saved session. Three ways in:
 *  - "Try the demo farm": attaches to the seeded, fully set-up demo farm
 *    (GET /demo-session), shared by every device that picks it.
 *  - "Set up my farm": the normal setup wizard -> a new farm of their own.
 *  - "Restore my farm": a restore code from Settings on the old phone
 *    (POST /restore) re-attaches THIS phone to that farm -- the only way back
 *    after a reset/reinstall/new phone, since there are no accounts. For the
 *    team's farm this also restores Google Calendar ownership (farm_id based).
 * Bilingual on purpose: no language has been chosen yet at this point.
 */
export default function Welcome() {
  const setUser = useSessionStore((s) => s.setUser);
  const setFarm = useSessionStore((s) => s.setFarm);
  const setIsDemo = useSessionStore((s) => s.setIsDemo);
  const [loading, setLoading] = useState<"demo" | "restore" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRestore, setShowRestore] = useState(false);
  const [code, setCode] = useState("");
  const [showServer, setShowServer] = useState(false);
  const [serverUrl, setServerUrl] = useState(apiBase());
  const { t } = useT();

  async function tryDemo() {
    setLoading("demo");
    setError(null);
    const { data, error: err } = await api.GET("/demo-session");
    setLoading(null);
    if (err || !data) {
      setError("Ladang demo tidak dapat dimuatkan. / Could not load the demo farm -- check the connection.");
      return;
    }
    setUser(data.user);
    setFarm(data.farm);
    setIsDemo(true);
    router.replace("/(tabs)");
  }

  async function restore() {
    setLoading("restore");
    setError(null);
    const { data, error: err } = await api.POST("/restore", { body: { code: code.trim() } });
    setLoading(null);
    if (err || !data) {
      setError("Kod tidak dikenali. / Restore code not recognised -- check it on your old phone's Settings.");
      return;
    }
    setUser(data.user);
    setFarm(data.farm);
    setIsDemo(false);
    // The gate decides: setup finished -> tabs, otherwise back into the wizard.
    router.replace("/");
  }

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <View style={styles.hero}>
        <Image source={LOGO} style={styles.logo} resizeMode="contain" accessibilityLabel="PepperDex Sarawak" />
        <Text style={styles.tagline}>Di mana penyakit akan merebak seterusnya, dan bila.</Text>
        <Text style={styles.taglineEn}>Where foot rot travels next, and when.</Text>
      </View>

      <View style={styles.actions}>
        <PrimaryButton label="Cuba ladang demo · Try the demo farm" onPress={tryDemo} loading={loading === "demo"} />
        <Text style={styles.hint}>
          Ladang contoh yang sudah lengkap. / A ready-made farm with diagnoses, agents and 3D terrain.
        </Text>

        <PrimaryButton
          label="Daftar ladang saya · Set up my farm"
          variant="secondary"
          onPress={() => router.push("/(setup)/register")}
        />
        <Text style={styles.hint}>Jalan sekeliling blok anda. / Walk your own blocks (about 5 minutes).</Text>

        {!showRestore ? (
          <Pressable onPress={() => setShowRestore(true)} hitSlop={8}>
            <Text style={styles.link}>Pulihkan ladang saya · Restore my farm</Text>
          </Pressable>
        ) : (
          <View style={styles.restoreBox}>
            <Text style={styles.restoreLabel}>
              Kod pemulihan (Tetapan di telefon lama) / Restore code (Settings on your old phone)
            </Text>
            <TextInput
              value={code}
              onChangeText={setCode}
              style={styles.input}
              placeholder="ABC-DEF-GHJ"
              autoCapitalize="characters"
              autoCorrect={false}
              maxLength={20}
            />
            <PrimaryButton
              label="Pulihkan · Restore"
              onPress={restore}
              loading={loading === "restore"}
              disabled={code.replace(/[^a-z0-9]/gi, "").length < 9}
            />
          </View>
        )}

        {error && <Text style={styles.error}>{error}</Text>}

        {!showServer ? (
          <Pressable onPress={() => setShowServer(true)} hitSlop={8}>
            <Text style={styles.serverLink}>
              {t("server_change").replace("{url}", serverUrl.replace(/^https?:\/\//, ""))}
            </Text>
          </Pressable>
        ) : (
          <ServerAddressField onSaved={() => setServerUrl(apiBase())} />
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flexGrow: 1,
    backgroundColor: colors.background,
    padding: spacing.lg,
    justifyContent: "space-between",
  },
  hero: { flex: 1, minHeight: 260, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  logo: { width: "80%", height: 120 },
  tagline: { fontFamily: fonts.displayBold, fontSize: 17, color: colors.brandDark, textAlign: "center" },
  taglineEn: { fontFamily: fonts.body, fontSize: 14, color: colors.textMuted, textAlign: "center" },
  actions: { gap: spacing.sm, paddingBottom: spacing.xl },
  hint: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted, textAlign: "center", marginBottom: spacing.sm },
  link: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.brandGreen, textAlign: "center", padding: spacing.sm },
  restoreBox: {
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  restoreLabel: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  input: {
    fontFamily: fonts.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 18,
    letterSpacing: 2,
    textAlign: "center",
    backgroundColor: colors.background,
  },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.danger, textAlign: "center" },
  serverLink: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted, textAlign: "center", marginTop: spacing.sm },
});
