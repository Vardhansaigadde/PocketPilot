/// The pairing the app got from the laptop's QR code, and where it is saved.
///
/// The QR code is a link like
///   `https://192.168.1.5:8765/?token=abc...&ca=<sha256 of the laptop's own CA>`
/// The token lets the phone in; the CA fingerprint lets the app trust exactly this
/// laptop's certificate (so there is no "not private" warning).
library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class Pairing {
  const Pairing({
    required this.host,
    required this.port,
    required this.token,
    required this.caSha256,
  });

  final String host;
  final int port;
  final String token;
  final String caSha256; // lowercase hex

  /// The phone page on the laptop (the same page a browser opens from the QR code).
  Uri get pageUrl => Uri(
        scheme: 'https',
        host: host,
        port: port,
        path: '/',
        queryParameters: {'token': token},
      );

  Uri get caUrl => Uri(scheme: 'https', host: host, port: port, path: '/pocketpilot-ca.crt');

  Pairing withHost(String newHost, int newPort) =>
      Pairing(host: newHost, port: newPort, token: token, caSha256: caSha256);

  Map<String, dynamic> toJson() => {'host': host, 'port': port, 'token': token, 'ca': caSha256};

  static Pairing fromJson(Map<String, dynamic> j) => Pairing(
        host: j['host'] as String,
        port: j['port'] as int,
        token: j['token'] as String,
        caSha256: j['ca'] as String,
      );

  /// Reads a scanned QR code. Throws [PairingError] with a message for the user.
  static Pairing fromQr(String text) {
    final uri = Uri.tryParse(text.trim());
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw const PairingError('That QR code is not a PocketPilot code.');
    }
    if (uri.scheme == 'http') {
      throw const PairingError('PocketPilot is running without HTTPS. Start it with: python run.py');
    }
    final token = uri.queryParameters['token'] ?? '';
    final ca = (uri.queryParameters['ca'] ?? '').toLowerCase();
    if (uri.scheme != 'https' || token.isEmpty) {
      throw const PairingError('That QR code is not a PocketPilot code.');
    }
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(ca)) {
      throw const PairingError('This QR code is from an older PocketPilot. Update it on the laptop, '
          'restart it, and scan the new code.');
    }
    return Pairing(host: uri.host, port: uri.hasPort ? uri.port : 8765, token: token, caSha256: ca);
  }
}

class PairingError implements Exception {
  const PairingError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Saved in Android's encrypted storage (the token is a secret).
class PairingStore {
  PairingStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _pairingKey = 'pairing';
  static const _caKey = 'ca_der';

  Future<(Pairing, List<int>)?> load() async {
    final p = await _storage.read(key: _pairingKey);
    final ca = await _storage.read(key: _caKey);
    if (p == null || ca == null) return null;
    return (Pairing.fromJson(jsonDecode(p) as Map<String, dynamic>), base64Decode(ca));
  }

  Future<void> save(Pairing pairing, List<int> caDer) async {
    await _storage.write(key: _pairingKey, value: jsonEncode(pairing.toJson()));
    await _storage.write(key: _caKey, value: base64Encode(caDer));
  }

  Future<void> clear() => _storage.deleteAll();
}
