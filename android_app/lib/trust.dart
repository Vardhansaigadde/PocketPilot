/// Trusting exactly one laptop: its own certificate authority (CA), pinned by fingerprint.
///
/// When pairing, the app downloads the laptop's CA certificate once and keeps it only if
/// its SHA-256 equals the fingerprint in the QR code. After that, every connection is
/// accepted only if the laptop's certificate was signed by that CA (checked by Android's
/// own crypto in MainActivity.kt). Nothing else is ever trusted.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';

import 'pairing.dart';

const _channel = MethodChannel('pocketpilot/trust');

String sha256Hex(List<int> bytes) => sha256.convert(bytes).toString();

/// PEM ("-----BEGIN CERTIFICATE-----...") -> DER bytes.
Uint8List pemToDer(String pem) {
  final body = pem
      .replaceAll(RegExp(r'-----(BEGIN|END) CERTIFICATE-----'), '')
      .replaceAll(RegExp(r'\s'), '');
  return base64Decode(body);
}

/// Downloads the laptop's CA certificate and checks it against the QR fingerprint.
/// The download itself can't be trusted yet (that is what we are setting up), which is
/// fine: a fake certificate can't have the same SHA-256 as the real one.
Future<Uint8List> fetchPinnedCa(Pairing pairing) async {
  final client = HttpClient()
    ..connectionTimeout = const Duration(seconds: 6)
    ..badCertificateCallback = (cert, host, port) => host == pairing.host && port == pairing.port;
  try {
    final request = await client.getUrl(pairing.caUrl);
    final response = await request.close().timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      throw const PairingError('The laptop did not send its certificate. Is PocketPilot running?');
    }
    final pem = await response.transform(utf8.decoder).join();
    final der = pemToDer(pem);
    if (sha256Hex(der) != pairing.caSha256) {
      throw const PairingError('The laptop\'s certificate does not match the QR code. Scan the code again '
          'on your own Wi-Fi.');
    }
    return der;
  } on PairingError {
    rethrow;
  } on Exception {
    throw const PairingError('Can\'t reach the laptop. Check the phone and laptop are on the same Wi-Fi.');
  } finally {
    client.close(force: true);
  }
}

/// True if [leafDer] (the certificate the laptop just showed) was signed by [caDer]
/// and is in date. Done by Android itself (java.security) in MainActivity.kt.
Future<bool> signedByPinnedCa(Uint8List leafDer, Uint8List caDer) async {
  try {
    return await _channel.invokeMethod<bool>('verify', {'leaf': leafDer, 'ca': caDer}) ?? false;
  } on PlatformException {
    return false;
  }
}
