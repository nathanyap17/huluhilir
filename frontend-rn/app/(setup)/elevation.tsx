import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../../src/api/client";
import { PrimaryButton } from "../../src/components/PrimaryButton";
import { ScreenContainer, ScreenFooter } from "../../src/components/ScreenContainer";
import { useSessionStore } from "../../src/store/sessionStore";
import { colors, fonts, radius, spacing } from "../../src/constants/theme";

interface ElevationQuestion {
  block_a_id: string;
  block_b_id: string;
  block_a_label: string | null;
  block_b_label: string | null;
}

interface ElevationQuestionsResponse {
  elevation_tier: "minimal" | "optimised";
  questions: ElevationQuestion[];
}

interface ResolveElevationResult {
  setup_completed: boolean;
  derived_automatically: boolean;
  questions_answered: number;
  conflicts_logged: number;
}

/**
 * §9.11 -- Elevation Resolution. MINIMAL tier asks every pair (pepperdex-
 * rules §3: the farmer's answer always wins); OPTIMISED tier only asks the
 * pairs the barometer could not separate (Δh < 2.0m). The GET/POST bodies
 * here are untyped `dict`s in the real backend (app/routers/setup.py), not
 * Pydantic response_models, so openapi-typescript can't give them real
 * shapes -- the interfaces above mirror the router's actual return dict by
 * hand, kept in sync with that file rather than a generated type.
 */
export default function ElevationScreen() {
  const farm = useSessionStore((s) => s.farm);
  const setFarm = useSessionStore((s) => s.setFarm);
  const [answers, setAnswers] = useState<Record<string, "a_higher" | "b_higher">>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResolveElevationResult | null>(null);

  const questionsQuery = useQuery({
    queryKey: ["elevation-questions", farm?.farm_id],
    queryFn: async () => {
      const { data, error: err } = await api.GET("/farms/{farm_id}/elevation-questions", {
        params: { path: { farm_id: farm!.farm_id! } },
      });
      if (err) throw err;
      return data as unknown as ElevationQuestionsResponse;
    },
    enabled: !!farm,
  });

  const questions = questionsQuery.data?.questions ?? [];
  const allAnswered = questions.every((q) => answers[pairKey(q)] !== undefined);

  function pairKey(q: ElevationQuestion): string {
    return `${q.block_a_id}|${q.block_b_id}`;
  }

  async function handleResolve() {
    if (!farm) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST("/farms/{farm_id}/resolve-elevation", {
        params: { path: { farm_id: farm.farm_id! } },
        body: {
          answers: questions.map((q) => ({
            block_a_id: q.block_a_id,
            block_b_id: q.block_b_id,
            answer: answers[pairKey(q)],
          })),
        },
      });
      if (err) throw new Error("Could not resolve elevation");
      const resolved = data as unknown as ResolveElevationResult;
      setResult(resolved);
      setFarm({ ...farm, setup_completed_at: new Date().toISOString() });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <ScreenContainer setupStep={3}>
        <Text style={styles.title}>Farm slope worked out</Text>
        {result.derived_automatically ? (
          <Text style={styles.subtitle}>
            Your barometer figured out the slope automatically — you weren't asked anything.
          </Text>
        ) : (
          <Text style={styles.subtitle}>
            Answered {result.questions_answered} question{result.questions_answered === 1 ? "" : "s"}.
          </Text>
        )}
        {result.conflicts_logged > 0 && (
          <Text style={styles.subtitle}>
            {result.conflicts_logged} sensor disagreement{result.conflicts_logged === 1 ? "" : "s"}{" "}
            logged — your answer was always used.
          </Text>
        )}
        <ScreenFooter>
          <PrimaryButton label="See my farm" onPress={() => router.replace("/(setup)/validator")} />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  if (questionsQuery.isLoading) {
    return (
      <ScreenContainer setupStep={3}>
        <Text style={styles.subtitle}>Loading…</Text>
      </ScreenContainer>
    );
  }

  if (questions.length === 0) {
    return (
      <ScreenContainer setupStep={3}>
        <Text style={styles.title}>No questions needed</Text>
        <Text style={styles.subtitle}>
          {questionsQuery.data?.elevation_tier === "optimised"
            ? "Your barometer separated every block clearly."
            : "Only one block was captured — nothing to compare yet."}
        </Text>
        <ScreenFooter>
          <PrimaryButton label="Continue" onPress={handleResolve} loading={submitting} />
        </ScreenFooter>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer setupStep={3}>
      <Text style={styles.title}>Which block is higher?</Text>
      <Text style={styles.subtitle}>
        Your answer always wins, even if a sensor disagrees.
      </Text>

      {questions.map((q) => {
        const key = pairKey(q);
        return (
          <View key={key} style={styles.questionBox}>
            <Text style={styles.label}>
              {q.block_a_label ?? "Block A"} vs {q.block_b_label ?? "Block B"}
            </Text>
            <View style={styles.row}>
              <Pressable
                onPress={() => setAnswers((a) => ({ ...a, [key]: "a_higher" }))}
                style={[styles.chip, answers[key] === "a_higher" && styles.chipActive]}
              >
                <Text style={[styles.chipLabel, answers[key] === "a_higher" && styles.chipLabelActive]}>
                  {q.block_a_label ?? "Block A"} is higher
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setAnswers((a) => ({ ...a, [key]: "b_higher" }))}
                style={[styles.chip, answers[key] === "b_higher" && styles.chipActive]}
              >
                <Text style={[styles.chipLabel, answers[key] === "b_higher" && styles.chipLabelActive]}>
                  {q.block_b_label ?? "Block B"} is higher
                </Text>
              </Pressable>
            </View>
          </View>
        );
      })}

      {error && <Text style={styles.error}>{error}</Text>}

      <ScreenFooter>
        <PrimaryButton label="Confirm" onPress={handleResolve} disabled={!allAnswered} loading={submitting} />
      </ScreenFooter>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.brandDark },
  subtitle: { fontFamily: fonts.body, fontSize: 15, color: colors.textMuted },
  label: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.text },
  questionBox: {
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    flexGrow: 1,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.background,
    alignItems: "center",
  },
  chipActive: { backgroundColor: colors.brandGreen, borderColor: colors.brandGreen },
  chipLabel: { fontFamily: fonts.body, color: colors.text, fontSize: 13 },
  chipLabelActive: { color: "#fff", fontFamily: fonts.bodySemi },
  error: { fontFamily: fonts.body, color: colors.danger, fontSize: 14 },
});
