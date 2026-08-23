import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'models.dart';
import 'speech.dart';
import 'providers.dart';
import 'theme.dart';

/// The real 3D terrain implementation -- IDW-generated terraced terrain,
/// low-poly vine clusters per block, dashed downhill flow lines, and
/// click-to-select, all rendered by classic (non-module) Three.js r128
/// inside a bundled WebView. See docs/BUILD_LOG.md "3D terrain viability
/// spike" for why classic scripts are required (ES modules fail CORS over
/// file://) and "Full 3D terrain implementation" for what's approximated
/// vs. built from real data.
///
/// Node layout is synthetic (by elevation_rank only, never real lat/lon --
/// huluhilir-rules skill §4); flow lines are the REAL flow_edges from the
/// backend, not re-derived client-side, so this stays a single source of
/// truth with compute_spread's actual output.
class Terrain3DView extends ConsumerStatefulWidget {
  final List<TerrainNode> nodes;
  final List<FlowEdgeModel> edges;
  final Map<String, String> labels;
  final Widget Function(String blockId, VoidCallback? onClose) profileBuilder;
  final double height;

  const Terrain3DView({
    super.key,
    required this.nodes,
    required this.edges,
    required this.labels,
    required this.profileBuilder,
    this.height = 420,
  });

  @override
  ConsumerState<Terrain3DView> createState() => _Terrain3DViewState();
}

class _Terrain3DViewState extends ConsumerState<Terrain3DView> {
  late final WebViewController _controller;
  bool _ready = false;
  String? _selectedBlockId;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(AppColors.cream)
      ..addJavaScriptChannel('FlutterBridge', onMessageReceived: _onBridgeMessage)
      ..loadFlutterAsset('assets/terrain/terrain.html');
  }

  @override
  void didUpdateWidget(covariant Terrain3DView old) {
    super.didUpdateWidget(old);
    if (_ready && (old.nodes != widget.nodes || old.edges != widget.edges)) {
      _sendData();
    }
  }

  void _onBridgeMessage(JavaScriptMessage message) {
    final msg = message.message;
    if (msg == 'ready') {
      setState(() => _ready = true);
      _sendData();
    } else if (msg.startsWith('select:')) {
      setState(() => _selectedBlockId = msg.substring('select:'.length));
    } else if (msg == 'deselect') {
      resetVoiceLabel();
      // The scene closes the card itself when the pointer leaves the block
      // (mouse) or the finger lifts (touch). There is no X to press.
      setState(() => _selectedBlockId = null);
    }
  }

  void _sendData() {
    final payload = {
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
    };
    _controller.runJavaScript('window.renderTerrain(${jsonEncode(payload)});');
  }



  @override
  void dispose() {
    // Safety: if this widget is torn down mid-touch, don't leave the
    // dashboard's ListView permanently non-scrollable.
    Future.microtask(() {
      if (ref.context.mounted) ref.read(terrainInteractingProvider.notifier).state = false;
    });
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.nodes.isEmpty) {
      return SizedBox(
        height: 200,
        child: Center(child: Text('Tiada blok lagi', style: AppText.sans(color: AppColors.oliveLight))),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: SizedBox(
        height: widget.height,
        child: Stack(children: [
          // Disables the dashboard's outer ListView scroll physics for the
          // duration of the touch, via terrainInteractingProvider, rather
          // than relying on webview_flutter's gestureRecognizers to win the
          // native gesture arena against the ancestor Scrollable -- that was
          // NOT reliable on-device (confirmed via instrumented pointer
          // logging: the WebView's own viewport was still shifting mid-touch
          // even with an EagerGestureRecognizer set). See
          // docs/BUILD_LOG.md "Full 3D terrain implementation".
          Listener(
            onPointerDown: (_) => ref.read(terrainInteractingProvider.notifier).state = true,
            onPointerUp: (_) => ref.read(terrainInteractingProvider.notifier).state = false,
            onPointerCancel: (_) => ref.read(terrainInteractingProvider.notifier).state = false,
            child: WebViewWidget(controller: _controller),
          ),
          if (!_ready)
            const Positioned.fill(
              child: ColoredBox(
                color: AppColors.cream,
                child: Center(child: CircularProgressIndicator(color: AppColors.olive)),
              ),
            ),
          if (_selectedBlockId != null)
            // left AND right, not right alone. With only `right` set the card
            // gets UNBOUNDED width, and its header uses
            // `SizedBox(width: double.infinity)` -- so it laid out wider than
            // the Stack, putting its close button outside the parent's
            // bounds. Flutter does not hit-test outside those bounds, so the
            // X was visible (ClipRRect hid the overflow) but untappable.
            // The web view was already constrained on both sides, which is
            // why the same card closed correctly there.
            Positioned(
              top: 12,
              left: 12,
              right: 12,
              child: IgnorePointer(
                // On touch the finger is on the pillar, not the card, and on
                // a mouse the card must not swallow the pointer on its way
                // back to the scene -- either would strand the peek open.
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

