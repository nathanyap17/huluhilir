import { createAudioPlayer } from "expo-audio";
import { useCallback } from "react";
import { api } from "../api/client";
import { apiBase } from "../constants/config";
import { useSessionStore } from "../store/sessionStore";

/**
 * Every user-facing string carries a speech_template_id (pepperdex-rules
 * skill §8) -- literacy is not assumed. This calls POST /speech/render,
 * which degrades to `audio_uri: null` rather than erroring
 * (app/routers/speech.py), so a farmer who cannot hear the advice can still
 * read the text that is already on screen; playback here is enhancement,
 * never a requirement for the screen to be usable.
 */
export function useSpeak() {
  const language = useSessionStore((s) => s.user?.language_pref ?? "ms");

  const speak = useCallback(
    async (templateId: string, slots: Record<string, string> = {}) => {
      try {
        const { data, error } = await api.POST("/speech/render", {
          body: { template_id: templateId, slots, language, seed: 42 },
        });
        if (error || !data) return;
        const audioUri = (data as { audio_uri?: string | null }).audio_uri;
        if (!audioUri) return; // degraded to text-only; nothing to play
        const player = createAudioPlayer(`${apiBase()}${audioUri}`);
        player.play();
      } catch {
        // Speech is never on the critical path -- a network hiccup here
        // must not block or error the screen that called it.
      }
    },
    [language]
  );

  // Runtime strings (an agent's reason_ms) have no fixed template, so they go
  // through /speech/say, which speaks slots.text as-is.
  const speakText = useCallback(
    async (templateId: string, text: string) => {
      try {
        const { data, error } = await api.POST("/speech/say", {
          body: { template_id: templateId, slots: { text }, language, seed: 42 },
        });
        if (error || !data) return;
        const audioUri = (data as { audio_uri?: string | null }).audio_uri;
        if (!audioUri) return;
        createAudioPlayer(`${apiBase()}${audioUri}`).play();
      } catch {
        // never on the critical path
      }
    },
    [language]
  );

  return { speak, speakText };
}
