import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Throwaway viability spike -- NOT the real terrain view. Proves whether
/// Android WebView (via webview_flutter) can load ES-module Three.js from a
/// bundled Flutter asset and render WebGL, before investing in the full IDW
/// terrain generator. Delete once the real 3D terrain screen replaces it.
class Terrain3DSmokeTest extends StatefulWidget {
  const Terrain3DSmokeTest({super.key});

  @override
  State<Terrain3DSmokeTest> createState() => _Terrain3DSmokeTestState();
}

class _Terrain3DSmokeTestState extends State<Terrain3DSmokeTest> {
  late final WebViewController _controller;
  String _status = 'loading...';

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF5F2ED))
      ..addJavaScriptChannel(
        'FlutterBridge',
        onMessageReceived: (message) {
          setState(() => _status = 'Flutter received: ${message.message}');
        },
      )
      ..setNavigationDelegate(NavigationDelegate(
        onWebResourceError: (error) {
          setState(() => _status = 'WebResourceError: ${error.description}');
        },
      ))
      ..loadFlutterAsset('assets/terrain/smoke_test.html');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('3D smoke test: $_status')),
      body: WebViewWidget(controller: _controller),
    );
  }
}
