/// Playback for agent output. docs/PROJECT_SPEC.md §3 L0.
///
/// Literacy is not assumed (huluhilir-rules §7), so every user-facing line
/// must be speakable. The backend composes and caches the audio; this only
/// plays it.
///
/// **Never blocks the caller's UI on success.** If synthesis fails the
/// server returns `audio_uri: null` with a `degraded_reason` rather than an
/// error, and this surfaces that as a message instead of throwing — a
/// farmer who cannot hear the advice must still be able to read it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:just_audio/just_audio.dart';

import 'providers.dart';

final _player = AudioPlayer();

/// Separate player for the farmer's own recorded block labels, so starting a
/// label does not cut off a diagnosis being read aloud (and vice versa).
final _labelPlayer = AudioPlayer();

/// The block whose label is currently playing. Guards against a peek
/// re-triggering playback on every rebuild -- hover fires a lot of frames.
String? _labelPlayingFor;

/// Play a block's recorded voice label, at most once per block per peek.
///
/// Called when a block is hovered or held rather than from a button: during a
/// touch peek the finger is pinned to the pillar, so a button on the card
/// cannot be reached. Hearing the label is what makes the peek usable on a
/// phone.
///
/// This is playback of stored audio. Nothing transcribes it (huluhilir-rules
/// section 1), which is exactly why an Iban label works here.
Future<void> playVoiceLabel(String url, String blockId) async {
  if (_labelPlayingFor == blockId) return;
  _labelPlayingFor = blockId;
  try {
    await _labelPlayer.stop();
    await _labelPlayer.setUrl(url);
    await _labelPlayer.play();
  } catch (_) {
    // A label that will not play must never interrupt the peek. Silence is
    // an acceptable degradation; an error dialog over the card is not.
  }
}

/// Called when the peek ends, so the next peek at the same block replays.
void resetVoiceLabel() => _labelPlayingFor = null;

/// Speak a line, showing a snackbar only when something actually went wrong.
Future<void> speak(
  BuildContext context,
  WidgetRef ref,
  String text, {
  String? templateId,
  String language = 'ms',
}) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final api = ref.read(apiClientProvider);
    final result = await api.say(text, language: language, templateId: templateId);

    // Iban is machine-translated with no Iban voice available, so the UI
    // discloses both rather than letting it pass as verified Iban speech.
    if (language == 'iba') {
      final translated = result['text'] as String?;
      final src = result['translation_source'];
      if (translated != null && translated.isNotEmpty) {
        messenger.showSnackBar(SnackBar(
          duration: const Duration(seconds: 6),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(translated),
              const SizedBox(height: 4),
              Text(
                src == 'machine'
                    ? 'Terjemahan mesin · suara Melayu (tiada suara Iban)'
                    : 'Terjemahan gagal — dibaca dalam bahasa asal',
                style: const TextStyle(fontSize: 11),
              ),
            ],
          ),
        ));
      }
    }

    final uri = result['audio_uri'] as String?;
    if (uri == null) {
      messenger.showSnackBar(SnackBar(
        content: Text('Suara tidak tersedia: ${result['degraded_reason'] ?? "tidak diketahui"}'),
      ));
      return;
    }

    await _player.stop();
    await _player.setUrl(api.mediaUrl(uri));
    await _player.play();
  } catch (e) {
    messenger.showSnackBar(SnackBar(content: Text('Suara gagal: $e')));
  }
}
