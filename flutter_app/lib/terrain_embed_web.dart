/// Web half of the terrain embed split — the real 3D scene in a browser.
///
/// `webview_flutter` has no web implementation, so the dashboard used to
/// fall back to the 2D diagram in a browser. But `terrain.html` is already a
/// standalone page, so on web it can simply be an `<iframe>` — the same
/// scene, the same file, no second 3D implementation to keep in sync.
///
/// Communication is `postMessage` in both directions, which is the web
/// equivalent of the `JavaScriptChannel` the Android path uses:
///   Flutter → scene:  `{type: 'render', payload: {...}}`
///   scene   → Flutter: `{type: 'select', blockId: '...'}`
///
/// The scene is told to listen for these by `terrain.html` itself, so both
/// platforms drive the identical `window.renderTerrain` entry point.
library;

import 'dart:js_interop';
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

const _viewType = 'huluhilir-terrain-iframe';

/// Flutter web serves bundled assets under a second `assets/` segment, so the
/// asset key `assets/terrain/terrain.html` is reachable at this URL.
const _terrainUrl = 'assets/assets/terrain/terrain.html';

bool _registered = false;
final _frames = <String, web.HTMLIFrameElement>{};

void _register() {
  if (_registered) return;
  _registered = true;
  ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
    final frame = web.document.createElement('iframe') as web.HTMLIFrameElement
      ..src = _terrainUrl
      ..style.border = 'none'
      ..style.width = '100%'
      ..style.height = '100%';
    _frames['$viewId'] = frame;
    return frame;
  });
}

class _TerrainEmbed extends StatefulWidget {
  final String payloadJson;
  final void Function(String? blockId) onSelect;
  const _TerrainEmbed({required this.payloadJson, required this.onSelect});

  @override
  State<_TerrainEmbed> createState() => _TerrainEmbedState();
}

class _TerrainEmbedState extends State<_TerrainEmbed> {
  int? _viewId;
  JSFunction? _listener;

  @override
  void initState() {
    super.initState();
    _register();
    // One window-level listener for selections posted back by the scene.
    final listener = (web.MessageEvent event) {
      final data = event.data;
      if (data == null) return;
      final text = data.dartify()?.toString() ?? '';
      // Cheap containment check rather than parsing every message on the
      // window: other Flutter web plumbing posts here too.
      // deselect is checked FIRST: 'huluhilir-deselect' also contains the
      // substring 'huluhilir-'  and a looser select check would swallow it.
      // The scene says when it is alive. Pushing on this signal is what makes
      // the first paint reliable: the blind retry below is a backstop, not the
      // mechanism, and on a slow iframe it used to exhaust before the page
      // could listen -- leaving an empty ground plane until re-entry.
      if (text.contains('huluhilir-ready')) {
        _push();
        return;
      }
      if (text.contains('huluhilir-deselect')) {
        widget.onSelect(null);
        return;
      }
      if (!text.contains('huluhilir-select')) return;
      final match = RegExp(r'huluhilir-select:([A-Za-z0-9_-]+)').firstMatch(text);
      if (match != null) widget.onSelect(match.group(1)!);
    }.toJS;
    _listener = listener;
    web.window.addEventListener('message', listener);
  }

  @override
  void dispose() {
    if (_listener != null) web.window.removeEventListener('message', _listener!);
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _TerrainEmbed oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.payloadJson != widget.payloadJson) _push();
  }

  /// The iframe may not have finished loading when the payload is ready, so
  /// this retries briefly rather than dropping the only render call. The
  /// scene ignores repeated identical renders, so an extra one is harmless.
  void _push() {
    final frame = _frames['$_viewId'];
    if (frame == null) return;
    var attempts = 0;
    void send() {
      frame.contentWindow?.postMessage(
        'huluhilir-render:${widget.payloadJson}'.toJS,
        '*'.toJS,
      );
      attempts++;
      if (attempts < 8) {
        Future.delayed(const Duration(milliseconds: 350), send);
      }
    }

    send();
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(
      viewType: _viewType,
      onPlatformViewCreated: (id) {
        _viewId = id;
        _push();
      },
    );
  }
}

Widget buildTerrainEmbed({
  required String payloadJson,
  required void Function(String? blockId) onSelect,
}) =>
    _TerrainEmbed(payloadJson: payloadJson, onSelect: onSelect);
