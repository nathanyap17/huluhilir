import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, AppState, Linking, Pressable, ScrollView, Share, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../src/api/client";
import { PrimaryButton } from "../src/components/PrimaryButton";
import { ServerAddressField } from "../src/components/ServerAddressField";
import { apiBase } from "../src/constants/config";
import { useT } from "../src/i18n";
import { useSessionStore } from "../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../src/constants/theme";

type LanguagePref = "ms" | "iba" | "en";
const LANGUAGES: { value: LanguagePref; label: string }[] = [
  { value: "ms", label: "Bahasa Malaysia" },
  { value: "iba", label: "Jaku Iban" },
  { value: "en", label: "English" },
];

/**
 * §9.16 -- top-right icon, not a 4th tab (confirmed placement,
 * docs/VALIDATION_CHECKLIST.md decision #8). elevation_tier is read-only
 * display -- sensor detection is automatic, never a farmer-facing toggle
 * (docs/PROJECT_SPEC.md §4). Reset is long-press only, never a visible
 * one-tap control.
 *
 * Language and farm name are editable (v1 parity, restored 2026-09-20).
 * "Connected apps" is where external integrations (MCP-style, currently the
 * device Calendar) are linked/unlinked. Linking only records consent and
 * device permission -- every calendar event is still a draft the farmer
 * approves one by one (pepperdex-rules 13), never written automatically.
 */
export default function SettingsScreen() {
  const user = useSessionStore((s) => s.user);
  const farm = useSessionStore((s) => s.farm);
  const setUser = useSessionStore((s) => s.setUser);
  const setFarm = useSessionStore((s) => s.setFarm);
  const clear = useSessionStore((s) => s.clear);
  const isDemo = useSessionStore((s) => s.isDemo);
  const { t } = useT();
  const [restoreCode, setRestoreCode] = useState<string | null>(null);

  // Restore code: the only way back to this farm from a new/reset phone.
  // Not for the shared demo farm (the backend refuses one anyway).
  useEffect(() => {
    if (isDemo || !farm?.farm_id) return;
    fetch(`${apiBase()}/farms/${farm.farm_id}/restore-code`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setRestoreCode(d?.code ?? null))
      .catch(() => setRestoreCode(null));
  }, [isDemo, farm?.farm_id]);

  function shareRestoreCode() {
    if (restoreCode) Share.share({ message: `PepperDex ${farm?.name ?? ""} -- ${restoreCode}` });
  }

  function rotateRestoreCode() {
    Alert.alert(t("restore_new_title"), t("restore_new_body"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("restore_new_confirm"),
        style: "destructive",
        onPress: async () => {
          const r = await fetch(`${apiBase()}/farms/${farm?.farm_id}/restore-code/rotate`, { method: "POST" });
          const d = r.ok ? await r.json() : null;
          if (d?.code) setRestoreCode(d.code);
        },
      },
    ]);
  }
  const [confirming, setConfirming] = useState(false);
  const [farmName, setFarmName] = useState(farm?.name ?? "");
  const [savingName, setSavingName] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [googleLinked, setGoogleLinked] = useState<boolean | null>(null);
  // Google is linked to ANOTHER farm (the team's demo phone). One Google token
  // per backend, so this device keeps approvals in the app instead.
  const [googleElsewhere, setGoogleElsewhere] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);

  async function checkGoogleStatus() {
    try {
      const res = await fetch(`${apiBase()}/api/calendar/status?farm_id=${farm?.farm_id ?? ""}`);
      const data = await res.json();
      setGoogleLinked(data?.connected ?? false);
      setGoogleElsewhere(data?.linked_elsewhere ?? false);
    } catch {
      setGoogleLinked(false);
    }
  }

  useEffect(() => {
    checkGoogleStatus();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        checkGoogleStatus();
      }
    });
    return () => sub.remove();
  }, []);

  async function changeLanguage(value: LanguagePref) {
    if (!user?.user_id || value === user.language_pref) return;
    if (isDemo) {
      // The demo user is shared by every demo device: change it here only.
      setUser({ ...user, language_pref: value });
      return;
    }
    const { data, error } = await api.PATCH("/users/{user_id}", {
      params: { path: { user_id: user.user_id } },
      body: { language_pref: value },
    });
    if (error || !data) {
      setMessage(t("msg_language_failed"));
      return;
    }
    setUser(data);
    setMessage(null);
  }

  async function saveFarmName() {
    const name = farmName.trim();
    if (!farm?.farm_id || !name || name === farm.name) return;
    setSavingName(true);
    const { data, error } = await api.PATCH("/farms/{farm_id}", {
      params: { path: { farm_id: farm.farm_id } },
      body: { name },
    });
    setSavingName(false);
    if (error || !data) {
      setMessage(t("msg_rename_failed"));
      return;
    }
    setFarm(data);
    setMessage(t("msg_renamed"));
  }



  async function linkGoogleCalendar() {
    setGoogleBusy(true);
    try {
      const farmParam = farm?.farm_id ? `?farm_id=${farm.farm_id}` : "";
      const res = await fetch(`${apiBase()}/api/calendar/auth-url${farmParam}`);
      const data = await res.json();
      if (res.status === 409) {
        setGoogleElsewhere(true);
        throw new Error(t("google_elsewhere"));
      }
      if (data?.auth_url) {
        await Linking.openURL(data.auth_url);
      } else {
        throw new Error(t("msg_calendar_failed"));
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : t("msg_calendar_failed"));
    } finally {
      setGoogleBusy(false);
    }
  }

  async function unlinkGoogleCalendar() {
    setGoogleBusy(true);
    try {
      await fetch(`${apiBase()}/api/calendar/google?farm_id=${farm?.farm_id ?? ""}`, { method: "DELETE" });
      await checkGoogleStatus();
      setMessage(t("msg_calendar_unlinked"));
    } finally {
      setGoogleBusy(false);
    }
  }

  function handleResetPress() {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000);
      return;
    }
    Alert.alert(t("reset_title"), t("reset_body"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("reset"),
        style: "destructive",
        onPress: () => {
          clear();
          router.replace("/");
        },
      },
    ]);
    setConfirming(false);
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {message && <Text style={styles.message}>{message}</Text>}

      <Text style={styles.section}>{t("settings_language")}</Text>
      <View style={styles.chips}>
        {LANGUAGES.map((l) => {
          const active = (user?.language_pref ?? "ms") === l.value;
          return (
            <Pressable
              key={l.value}
              onPress={() => changeLanguage(l.value)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>{l.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {user?.language_pref === "iba" && <Text style={styles.label}>{t("settings_iban_note")}</Text>}

      <Text style={styles.section}>{t("settings_farm_name")}</Text>
      {isDemo ? (
        <Text style={styles.label}>{t("demo_farm_note")}</Text>
      ) : (
      <View style={styles.nameRow}>
        <TextInput
          value={farmName}
          onChangeText={setFarmName}
          style={styles.input}
          maxLength={80}
          placeholder={t("settings_farm_placeholder")}
        />
        <PrimaryButton
          label={t("settings_save")}
          onPress={saveFarmName}
          loading={savingName}
          disabled={!farmName.trim() || farmName.trim() === farm?.name}
        />
      </View>
      )}

      <View style={styles.row}>
        <Text style={styles.label}>{t("settings_elevation")}</Text>
        <Text style={styles.value}>{farm?.elevation_tier === "optimised" ? t("tier_optimised") : t("tier_minimal")}</Text>
      </View>

      <Text style={styles.section}>{t("settings_connected")}</Text>
      <View style={styles.appCard}>
        <View style={styles.appText}>
          <Text style={styles.value}>Google Calendar</Text>
          <Text style={styles.label}>
            {googleLinked ? t("google_linked") : googleElsewhere ? t("google_elsewhere") : t("google_unlinked")}
          </Text>
        </View>
        {!googleElsewhere && (
          <PrimaryButton
            label={googleLinked ? t("unlink") : t("link")}
            variant={googleLinked ? "secondary" : "primary"}
            loading={googleBusy}
            onPress={googleLinked ? unlinkGoogleCalendar : linkGoogleCalendar}
          />
        )}
      </View>



      {!isDemo && restoreCode && (
        <>
          <Text style={styles.section}>{t("restore_section")}</Text>
          <View style={styles.codeCard}>
            <Text selectable style={styles.code}>{restoreCode}</Text>
            <Text style={styles.label}>{t("restore_hint")}</Text>
            <View style={styles.codeButtons}>
              <PrimaryButton label={t("restore_share")} onPress={shareRestoreCode} />
              <PrimaryButton label={t("restore_new")} variant="secondary" onPress={rotateRestoreCode} />
            </View>
          </View>
        </>
      )}

      <Text style={styles.section}>{t("server_section")}</Text>
      <ServerAddressField />

      <View style={styles.spacer} />

      <PrimaryButton
        label={confirming ? t("reset_confirm") : t("reset_press")}
        onPress={handleResetPress}
        variant="danger"
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: spacing.sm, flexGrow: 1 },
  message: {
    fontFamily: fonts.body,
    color: colors.brandDark,
    fontSize: 13,
    backgroundColor: colors.surface,
    padding: spacing.sm,
    borderRadius: radius.sm,
  },
  section: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.brandDark, marginTop: spacing.md },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.brandGreen, borderColor: colors.brandGreen },
  chipLabel: { fontFamily: fonts.body, color: colors.text, fontSize: 14 },
  chipLabelActive: { color: "#fff", fontFamily: fonts.bodySemi },
  nameRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  input: {
    fontFamily: fonts.body,
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  appCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  appText: { flex: 1, gap: 2 },
  label: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
  value: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.text, },
  codeCard: {
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  code: { fontFamily: fonts.displayBold, fontSize: 26, letterSpacing: 3, color: colors.brandDark, textAlign: "center" },
  codeButtons: { flexDirection: "row", gap: spacing.sm },
  spacer: { height: spacing.xl },
});
