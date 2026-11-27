/// Pair once: scan the QR code that `python run.py` shows on the laptop.
library;

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'pairing.dart';
import 'remote_screen.dart';
import 'trust.dart';

class PairScreen extends StatefulWidget {
  const PairScreen({super.key, required this.store});

  final PairingStore store;

  @override
  State<PairScreen> createState() => _PairScreenState();
}

class _PairScreenState extends State<PairScreen> {
  final _scanner = MobileScannerController(formats: const [BarcodeFormat.qrCode]);
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _scanner.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    final text = capture.barcodes.firstOrNull?.rawValue;
    if (_busy || text == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final pairing = Pairing.fromQr(text);
      final caDer = await fetchPinnedCa(pairing);   // checked against the QR fingerprint
      await widget.store.save(pairing, caDer);
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => RemoteScreen(store: widget.store, pairing: pairing, caDer: caDer),
      ));
    } on PairingError catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('PocketPilot', style: text.headlineMedium),
              const SizedBox(height: 8),
              Text('On the laptop run  python run.py  and scan the QR code it shows. '
                  'Phone and laptop must be on the same Wi-Fi.', style: text.bodyLarge),
              const SizedBox(height: 20),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: MobileScanner(controller: _scanner, onDetect: _onDetect),
                ),
              ),
              const SizedBox(height: 16),
              if (_busy) const LinearProgressIndicator(),
              if (_error != null)
                Text(_error!, style: text.bodyLarge?.copyWith(color: Theme.of(context).colorScheme.error)),
            ],
          ),
        ),
      ),
    );
  }
}
