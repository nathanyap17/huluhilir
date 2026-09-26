import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text } from "react-native";
import { api } from "../../src/api/client";
import { Card } from "../../src/components/Card";
import { DemoBanner } from "../../src/components/DemoBanner";
import { PriorityActionCard } from "../../src/components/PriorityActionCard";
import { RainPulseCard } from "../../src/components/RainPulseCard";
import { useT, type StringKey } from "../../src/i18n";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, spacing } from "../../src/constants/theme";

/**
 * §9.1 (7-day Rain Pulse) + §9.2 (Priority Action + drawer) + §9.3 (Advisor
 * Summary). Renders usefully with zero photographs (pepperdex-rules §6):
 * the dashboard query has no dependency on any diagnosis having ever run.
 */
export default function HomeScreen() {
  const farm = useSessionStore((s) => s.farm);
  const { t, lang } = useT();

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

  const dashboard = dashboardQuery.data;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={dashboardQuery.isFetching} onRefresh={() => dashboardQuery.refetch()} />
      }
    >
      <Text style={styles.farmName}>{farm?.name}</Text>

      <DemoBanner />

      {dashboard && <RainPulseCard rainPulse={dashboard.rain_pulse} />}

      {dashboard && (
        <PriorityActionCard
          action={dashboard.top_action ?? null}
          drawer={dashboard.drawer ?? null}
          advisor={dashboard.advisor ?? null}
          blockState={
            dashboard.terrain_nodes.find((n) => n.block_id === dashboard.top_action?.block_id)?.current_state ?? null
          }
        />
      )}

      {dashboard?.advisor && (
        <Pressable onPress={() => router.push("/(tabs)/advisor")}>
          <Card quiet>
            <Text style={styles.cardLabel}>{t("advisor_label")}</Text>
            <Text style={styles.actionType}>{t(`urgency_${dashboard.advisor.urgency}` as StringKey)}</Text>
            <Text style={styles.cardSub}>{dashboard.advisor.reason_ms}</Text>
            {(lang === "en" ? dashboard.advisor.next_check_en : dashboard.advisor.next_check_ms) && (
              <Text style={styles.nextCheck}>
                {lang === "en" ? dashboard.advisor.next_check_en : dashboard.advisor.next_check_ms}
              </Text>
            )}
            <Text style={styles.linkText}>{t("ask_more")}</Text>
          </Card>
        </Pressable>
      )}

      {dashboard && dashboard.pending_neighbour_alerts > 0 && (
        <Card>
          <Text style={styles.cardLabel}>
            {t("neighbour_alerts", { n: dashboard.pending_neighbour_alerts })}
          </Text>
        </Card>
      )}

      {!dashboard && !dashboardQuery.isLoading && (
        <Card>
          <Text style={styles.cardSub}>{t("load_failed")}</Text>
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  // MOCK_DESIGN.md §5: 20 dp screen padding, 12 dp between stacked cards.
  scroll: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: 12, paddingBottom: spacing.xl },
  farmName: { fontFamily: fonts.display, fontSize: 30, lineHeight: 34, color: colors.brandDark, marginBottom: spacing.xs },
  cardLabel: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1.2, color: colors.textMuted, textTransform: "uppercase" },
  cardSub: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21, color: colors.textMuted },
  actionType: { fontFamily: fonts.displayBold, fontSize: 19, color: colors.text },
  // The next best check: the Advisor's one scheduled suggestion, so it reads
  // as the card's key line (2026-09-27).
  nextCheck: { fontFamily: fonts.bodySemi, fontSize: 15, lineHeight: 21, color: colors.text, paddingTop: spacing.xs },
  linkText: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.accentInk, paddingTop: spacing.xs },
});
