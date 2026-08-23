/// The 3D terrain, in a browser.
///
/// Mirrors `Terrain3DView` (the Android/WebView one) but embeds
/// `terrain.html` as an iframe, since `webview_flutter` has no web
/// implementation. The scene file, the payload shape, and the selection
/// event are all identical — only the transport differs — so there is one
/// 3D scene in this codebase, not two.
///
/// Selection opens the same native `profileBuilder` overlay the Android path
/// uses, rather than a second profile UI rendered inside the page.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'models.dart';
import 'speech.dart';
import 'terrain_embed_stub.dart' if (dart.library.js_interop) 'terrain_embed_web.dart';
import 'theme.dart';

class Terrain3DWebView extends ConsumerStatefulWidget {
  final List<TerrainNode> nodes;
  final List<FlowEdgeModel> edges;
  final Map<String, String> labels;
  final Widget Function(String blockId, VoidCallback? onClose) profileBuilder;
  final double height;

  const Terrain3DWebView({
    super.key,
    required this.nodes,
    required this.edges,
    required this.labels,
    required this.profileBuilder,
    this.height = 420,
  });

  @override
  ConsumerState<Terrain3DWebView> createState() => _Terrain3DWebViewState();
}

class _Terrain3DWebViewState extends ConsumerState<Terrain3DWebView> {
  String? _selectedBlockId;

  /// Identical to Terrain3DView's payload. Kept in the same snake_case shape
  /// the scene already parses so the two platforms cannot drift apart.
  String get _payloadJson => jsonEncode({
        'nodes': widget.nodes
            .map((n) => {
                  'block_id': n.blockId,
                  'label': widget.labels[n.blockId] ?? n.blockId.substring(0, 4),
                  'elevation_rank': n.elevationRank,
                  'current_state': n.currentState,
                })
            .toList(),
        'edges': widget.edges
            .map((e) => {
                  'from_block_id': e.fromBlockId,
                  'to_block_id': e.toBlockId,
                  'flow_weight': e.flowWeight,
                  'barrier': e.barrier,
                })
            .toList(),
      });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.card),
        child: Stack(children: [
          Positioned.fill(
            child: buildTerrainEmbed(
              payloadJson: _payloadJson,
              onSelect: (blockId) {
                if (blockId == null) resetVoiceLabel();
                if (mounted) setState(() => _selectedBlockId = blockId);
              },
            ),
          ),
          if (_selectedBlockId != null)
            Positioned(
              left: 12,
              right: 12,
              bottom: 12,
              child: IgnorePointer(
                ignoring: true,
                child: Material(
                  color: Colors.transparent,
                  child: widget.profileBuilder(_selectedBlockId!, null),
                ),
              ),
            ),
        ]),
      ),
    );
  }
}
