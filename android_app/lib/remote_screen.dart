/// The remote: the laptop's phone page inside the app, plus the native parts.
///
/// - Certificate: accepted only if the laptop's own CA (pinned when pairing) signed it.
/// - Microphone: Android permission, then the page's mic request is granted.
/// - Speech and vibration: the page asks the app (web/native.js), because Android's
///   web view can't speak (Telugu replies) or vibrate reliably on its own.
/// - Lost connection: asks the Wi-Fi where the laptop is now, and reconnects.
/// - Back button: a small menu (reload, find laptop, pair again).
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import 'discovery.dart';
import 'pair_screen.dart';
import 'pairing.dart';
import 'trust.dart';

/// The JavaScript channel web/native.js talks to.
const bridgeName = 'PocketPilotApp';

class RemoteScreen extends StatefulWidget {
  const RemoteScreen({super.key, required this.store, required this.pairing, required this.caDer});

  final PairingStore store;
  final Pairing pairing;
  final List<int> caDer;

  @override
  State<RemoteScreen> createState() => _RemoteScreenState();
}

class _RemoteScreenState extends State<RemoteScreen> {
  late Pairing _pairing = widget.pairing;
  late final Uint8List _ca = Uint8List.fromList(widget.caDer);
  final _tts = FlutterTts();
  late final WebViewController _web;
  String? _problem;          // shown over the page when the laptop can't be reached
  bool _searching = false;
  bool _wrongCertificate = false;

  @override
  void initState() {
    super.initState();
    _web = WebViewController(onPermissionRequest: _onPermission)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel(bridgeName, onMessageReceived: _onBridgeMessage)
      ..setNavigationDelegate(NavigationDelegate(
        onSslAuthError: _checkCertificate,
        onPageFinished: (_) {
          if (_problem != null && !_searching) setState(() => _problem = null);
        },
        onWebResourceError: (error) {
          if (error.isForMainFrame == true && !_wrongCertificate) _reconnect();
        },
      ));
    final android = _web.platform;
    if (android is AndroidWebViewController) {
      android.setMediaPlaybackRequiresUserGesture(false);
      android.setTextZoom(100);
    }
    _load();
  }

  @override
  void dispose() {
    _tts.stop();
    super.dispose();
  }

  void _load() => _web.loadRequest(_pairing.pageUrl);

  // -- native bridge (web/native.js sends {"do": "speak" | "stop" | "vibrate", ...}) ------
  Future<void> _onBridgeMessage(JavaScriptMessage message) async {
    final Map<String, dynamic> m;
    try {
      m = jsonDecode(message.message) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    switch (m['do']) {
      case 'speak':
        await _tts.stop();
        await _tts.setLanguage('${m['lang'] ?? 'en-IN'}');
        await _tts.speak('${m['text'] ?? ''}');
      case 'stop':
        await _tts.stop();
      case 'vibrate':
        final ms = m['ms'] is num ? (m['ms'] as num).toInt() : 20;
        ms >= 30 ? HapticFeedback.mediumImpact() : HapticFeedback.lightImpact();
    }
  }

  // -- the laptop's certificate --------------------------------------------------------
  // Android calls this because the laptop's certificate isn't from a public authority.
  // It's accepted only if the CA pinned when pairing signed it.
  Future<void> _checkCertificate(SslAuthError error) async {
    final leaf = error.certificate?.data;
    final ok = leaf != null && await signedByPinnedCa(leaf, _ca);
    if (ok) {
      await error.proceed();
    } else {
      await error.cancel();
      if (mounted) setState(() => _wrongCertificate = true);
    }
  }

  // -- microphone ----------------------------------------------------------------------
  Future<void> _onPermission(WebViewPermissionRequest request) async {
    final wantsMic = request.types.contains(WebViewPermissionResourceType.microphone);
    final granted = !wantsMic || (await Permission.microphone.request()).isGranted;
    granted ? await request.grant() : await request.deny();
  }

  // -- finding the laptop again --------------------------------------------------------
  Future<void> _reconnect() async {
    if (_searching) return;
    setState(() {
      _searching = true;
      _problem = 'Looking for your laptop on this Wi-Fi…';
    });
    final found = await discover(_pairing.token, _pairing.caSha256);
    if (!mounted) return;
    if (found != null) {
      if (found.host != _pairing.host || found.port != _pairing.port) {
        _pairing = _pairing.withHost(found.host, found.port);
        await widget.store.save(_pairing, _ca);       // remember the new address
      }
      setState(() {
        _problem = null;
        _searching = false;
      });
      _load();
    } else {
      setState(() {
        _searching = false;
        _problem = 'Can\'t find the laptop. Is PocketPilot running (python run.py), '
            'and is this phone on the same Wi-Fi?';
      });
    }
  }

  // -- menu (back button) --------------------------------------------------------------
  Future<void> _menu() async {
    await showModalBottomSheet<void>(
      context: context,
      builder: (sheet) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Icon(Icons.refresh),
            title: const Text('Reload'),
            onTap: () {
              Navigator.pop(sheet);
              _web.reload();
            },
          ),
          ListTile(
            leading: const Icon(Icons.wifi_find),
            title: const Text('Find the laptop again'),
            onTap: () {
              Navigator.pop(sheet);
              _reconnect();
            },
          ),
          ListTile(
            leading: const Icon(Icons.qr_code_scanner),
            title: const Text('Pair with a laptop again'),
            onTap: () {
              Navigator.pop(sheet);
              _repair();
            },
          ),
          ListTile(
            leading: const Icon(Icons.close),
            title: const Text('Close PocketPilot'),
            onTap: () => SystemNavigator.pop(),
          ),
        ]),
      ),
    );
  }

  Future<void> _repair() async {
    await widget.store.clear();
    if (!mounted) return;
    await Navigator.of(context)
        .pushReplacement(MaterialPageRoute(builder: (_) => PairScreen(store: widget.store)));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _menu();
      },
      child: Scaffold(
        body: SafeArea(
          child: Stack(children: [
            WebViewWidget(controller: _web),
            if (_wrongCertificate) _Banner(
              text: 'This laptop\'s certificate is not the one you paired with, so PocketPilot '
                  'didn\'t connect. If you reinstalled PocketPilot on the laptop, pair again.',
              action: 'Pair again',
              onAction: _repair,
            ) else if (_problem != null) _Banner(
              text: _problem!,
              action: _searching ? null : 'Try again',
              onAction: _reconnect,
            ),
          ]),
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text, required this.action, required this.onAction});

  final String text;
  final String? action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: ColoredBox(
        color: Theme.of(context).scaffoldBackgroundColor,
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(text, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 16),
              if (action == null) const CircularProgressIndicator()
              else FilledButton(onPressed: onAction, child: Text(action!)),
            ]),
          ),
        ),
      ),
    );
  }
}
