import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { apiBase } from "../constants/config";
import { Ionicons } from "@expo/vector-icons";
import { colors, fonts, radius, shadow, spacing } from "../constants/theme";
import { PrimaryButton } from "./PrimaryButton";

export interface CalendarProposal {
  proposal_id: string;
  farm_id: string;
  run_id?: string | null;
  recommendation_id?: string | null;
  title: string;
  start_time: string;
  end_time: string;
  description: string;
  location: string;
  status: "pending_approval" | "approved" | "rejected" | string;
  approved_by_farmer: boolean;
  approved_at?: string | null;
  google_event_id?: string | null;
  html_link?: string | null;
  created_at: string;
}

interface TreatmentProposalCardProps {
  proposal: CalendarProposal;
  onApproved?: (proposalId: string) => void;
  onRejected?: (proposalId: string) => void;
}

export function TreatmentProposalCard({
  proposal,
  onApproved,
  onRejected,
}: TreatmentProposalCardProps) {
  const [loading, setLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(proposal.status);
  const [htmlLink, setHtmlLink] = useState(proposal.html_link);

  const startDate = new Date(proposal.start_time);
  const endDate = new Date(proposal.end_time);

  const formattedDate = startDate.toLocaleDateString("ms-MY", {
    weekday: "long",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  const formattedTime = `${startDate.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })} - ${endDate.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })}`;

  async function handleApprove() {
    setLoading(true);
    try {
      const res = await fetch(
        `${apiBase()}/api/calendar/proposals/${proposal.proposal_id}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ farmer_confirmed: true }),
        }
      );
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Gagal meluluskan cadangan.");
      }
      const data = await res.json();
      setCurrentStatus("approved");
      if (data.html_link) {
        setHtmlLink(data.html_link);
      }
      // No html_link = approved in the app only (this farm doesn't own the
      // Google link, e.g. a judge's phone) -- say so, don't claim a sync.
      Alert.alert(
        "Jadual Disahkan",
        data.html_link
          ? "Rawatan telah dijadualkan ke Google Calendar melalui MCP."
          : "Kelulusan disimpan dalam aplikasi. (Google Calendar hanya disambungkan pada telefon pasukan.)"
      );
      onApproved?.(proposal.proposal_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ralat tidak diketahui";
      Alert.alert("Ralat Kelulusan", msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleReject() {
    setLoading(true);
    try {
      const res = await fetch(
        `${apiBase()}/api/calendar/proposals/${proposal.proposal_id}/reject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        }
      );
      if (!res.ok) throw new Error("Gagal membatalkan cadangan.");
      setCurrentStatus("rejected");
      onRejected?.(proposal.proposal_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ralat tidak diketahui";
      Alert.alert("Ralat", msg);
    } finally {
      setLoading(false);
    }
  }

  const isPending = currentStatus === "pending_approval";
  const isApproved = currentStatus === "approved" || currentStatus === "deployed";
  const isRejected = currentStatus === "rejected";

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.titleContainer}>
          <Ionicons name="calendar-outline" size={18} color={colors.accentInk} />
          <Text style={styles.headerTitle}>Cadangan Jadual Google Calendar</Text>
        </View>
        <View
          style={[
            styles.statusPill,
            isPending && styles.statusPillPending,
            isApproved && styles.statusPillApproved,
            isRejected && styles.statusPillRejected,
          ]}
        >
          <Text
            style={[
              styles.statusText,
              isPending && styles.statusTextPending,
              isApproved && styles.statusTextApproved,
              isRejected && styles.statusTextRejected,
            ]}
          >
            {isPending ? "Perlu Kelulusan" : isApproved ? "Dijadualkan" : "Dibatalkan"}
          </Text>
        </View>
      </View>

      <Text style={styles.treatmentTitle}>{proposal.title}</Text>

      <View style={styles.timeBox}>
        <Text style={styles.dateLabel}>{formattedDate}</Text>
        <Text style={styles.timeLabel}>{formattedTime}</Text>
      </View>

      {proposal.description ? (
        <Text style={styles.description}>{proposal.description}</Text>
      ) : null}

      <View style={styles.locationRow}>
        <Ionicons name="location-outline" size={14} color={colors.textMuted} />
        <Text style={styles.location}>{proposal.location}</Text>
      </View>

      {isPending && (
        // MOCK_DESIGN.md §7 A.15: two equally weighted choices -- consent is
        // never nudged toward Approve by size or position.
        <View style={styles.actionRow}>
          <View style={styles.half}>
            <PrimaryButton label="Luluskan" onPress={handleApprove} loading={loading} />
          </View>
          <View style={styles.half}>
            <PrimaryButton label="Tolak" variant="secondary" onPress={handleReject} disabled={loading} />
          </View>
        </View>
      )}

      {isApproved && htmlLink && (
        <Pressable
          style={styles.openCalendarBtn}
          onPress={() => Linking.openURL(htmlLink)}
        >
          <Text style={styles.openCalendarText}>Buka di Google Calendar</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    marginVertical: spacing.xs,
    ...shadow.card,
  },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  titleContainer: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1 },
  badgeIcon: { fontFamily: fonts.body, fontSize: 14 },
  headerTitle: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.textMuted, flexShrink: 1 },
  // Status pills stay OFF the four block-state hues (MOCK_DESIGN.md §3).
  statusPill: { paddingHorizontal: spacing.sm + 2, paddingVertical: 4, borderRadius: radius.pill },
  statusPillPending: { backgroundColor: colors.paperDeep },
  statusPillApproved: { backgroundColor: "#DDEBDF" },
  statusPillRejected: { backgroundColor: colors.background },
  statusText: { fontFamily: fonts.bodySemi, fontSize: 12 },
  statusTextPending: { color: colors.brandDark },
  statusTextApproved: { color: colors.brandGreen },
  statusTextRejected: { color: colors.textMuted },
  treatmentTitle: { fontFamily: fonts.displayBold, fontSize: 18, lineHeight: 23, color: colors.text },
  timeBox: {
    backgroundColor: colors.background,
    borderRadius: 14,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    gap: 2,
  },
  dateLabel: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.text },
  timeLabel: { fontFamily: fonts.mono, fontSize: 15, color: colors.accentInk },
  description: { fontFamily: fonts.body, fontSize: 14, color: colors.textMuted, lineHeight: 20 },
  locationRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  location: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
  actionRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  half: { flex: 1 },
  openCalendarBtn: { marginTop: spacing.xs, paddingVertical: spacing.sm, alignItems: "center" },
  openCalendarText: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.accentInk, textDecorationLine: "underline" },
});
