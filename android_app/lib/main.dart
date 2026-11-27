/// PocketPilot for Android: the phone remote for your laptop, as an installable app.
///
/// It shows the same phone page a browser shows (touchpad, voice, Approve cards,
/// Telugu) and adds what a browser can't do: trust exactly your laptop's certificate
/// (no warning), find the laptop again when its Wi-Fi address changes, and speak
/// replies (including Telugu) with the phone's own voice.
library;

import 'package:flutter/material.dart';

import 'pair_screen.dart';
import 'pairing.dart';
import 'remote_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PocketPilotApp());
}

class PocketPilotApp extends StatelessWidget {
  const PocketPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PocketPilot',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6366F1), brightness: Brightness.dark),
        scaffoldBackgroundColor: const Color(0xFF0B1020),
        useMaterial3: true,
      ),
      home: const StartScreen(),
    );
  }
}

/// Opens the remote if this phone is paired, otherwise the QR scanner.
class StartScreen extends StatefulWidget {
  const StartScreen({super.key});

  @override
  State<StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<StartScreen> {
  final _store = PairingStore();

  @override
  void initState() {
    super.initState();
    _route();
  }

  Future<void> _route() async {
    final saved = await _store.load();
    if (!mounted) return;
    final next = saved == null
        ? PairScreen(store: _store)
        : RemoteScreen(store: _store, pairing: saved.$1, caDer: saved.$2);
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => next));
  }

  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: CircularProgressIndicator()));
}
