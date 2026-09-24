import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { queryClient } from "../api/queryClient";
import {
  DEFAULT_API_BASE_URL,
  apiBase,
  normaliseServerAddress,
  saveApiBase,
  testServer,
} from "../constants/config";
import { colors, fonts, radius, spacing } from "../constants/theme";
import { useT } from "../i18n";
import { PrimaryButton } from "./PrimaryButton";

/**
 * Change which backend this phone talks to, without a rebuild. The laptop
 * running the local backend gets a new Wi-Fi address on a different hotspot
 * (observed 2026-09-24: 192.168.0.6 -> 172.23.213.109), which left every
 * screen blank. Type what `ipconfig` shows; the address is tested against
 * GET /health before it is saved, then every screen reloads.
 */
export function ServerAddressField({ onSaved }: { onSaved?: () => void }) {
  const { t } = useT();
  const [value, setValue] = useState(apiBase().replace(/^https?:\/\//, ""));
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  async function apply(raw: string) {
    const url = normaliseServerAddress(raw);
    if (!url) {
      setStatus({ ok: false, text: t("server_invalid") });
      return;
    }
    setBusy(true);
    setStatus(null);
    const ok = await testServer(url);
    setBusy(false);
    if (!ok) {
      setStatus({ ok: false, text: t("server_unreachable").replace("{url}", url) });
      return;
    }
    await saveApiBase(url);
    setValue(url.replace(/^https?:\/\//, ""));
    setStatus({ ok: true, text: t("server_saved").replace("{url}", url) });
    queryClient.invalidateQueries();
    onSaved?.();
  }

  return (
    <View style={styles.box}>
      <Text style={styles.hint}>{t("server_hint")}</Text>
      <TextInput
        value={value}
        onChangeText={setValue}
        style={styles.input}
        placeholder="172.23.213.109:8000"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />
      <View style={styles.row}>
        <PrimaryButton label={t("server_test_save")} onPress={() => apply(value)} loading={busy} />
        {apiBase() !== DEFAULT_API_BASE_URL && (
          <PrimaryButton label={t("server_reset")} variant="secondary" onPress={() => apply(DEFAULT_API_BASE_URL)} />
        )}
      </View>
      {status && <Text style={[styles.status, { color: status.ok ? colors.brandGreen : colors.danger }]}>{status.text}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surface },
  hint: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  input: {
    fontFamily: fonts.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 16,
    backgroundColor: colors.background,
  },
  row: { flexDirection: "row", gap: spacing.sm },
  status: { fontFamily: fonts.bodySemi, fontSize: 13, },
});
