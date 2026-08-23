/// Reading back a finished recording, without a `dart:io` dependency.
///
/// `AudioRecorder.stop()` hands back a filesystem path on Android and a blob
/// URL on web. Neither can be read with the same API, and importing
/// `dart:io` at all breaks the web build (`Unsupported operation:
/// _Namespace`), so this uses an HTTP fetch that both platforms can service:
/// `package:http`-free, via Dio, which is already a dependency.
///
/// On Android a plain path is not a URL, so it is turned into a `file://`
/// URI first. On web the blob URL is fetched directly by the browser.
library;

import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

/// Where the recorder should write. Web ignores the path entirely and
/// produces a blob, so an empty string is correct there rather than a
/// fabricated temp path that no filesystem will honour.
String recordingTarget() {
  if (kIsWeb) return '';
  // Relative name: the recorder resolves it against its own app-private
  // directory, which avoids needing path_provider or dart:io here.
  return 'voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
}

Future<Uint8List> readRecording(String source) async {
  final uri = source.startsWith('http') || source.startsWith('blob:')
      ? source
      : Uri.file(source).toString();
  final response = await Dio().get<List<int>>(
    uri,
    options: Options(responseType: ResponseType.bytes),
  );
  return Uint8List.fromList(response.data ?? const []);
}
