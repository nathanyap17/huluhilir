/// Non-web half of the terrain embed split.
///
/// Selected by conditional import on every platform except web. The web half
/// pulls in `dart:ui_web` and `dart:js_interop`, neither of which compiles
/// for Android — keeping them behind this split is what lets one dashboard
/// widget serve both without the mobile build ever seeing web-only imports.
library;

import 'package:flutter/material.dart';

/// Never called on mobile: the dashboard routes to the WebView-backed
/// `Terrain3DView` there. Present only to satisfy the conditional import.
Widget buildTerrainEmbed({
  required String payloadJson,
  required void Function(String blockId) onSelect,
}) =>
    const SizedBox.shrink();
