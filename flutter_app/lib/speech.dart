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
