import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:pocketpilot_app/discovery.dart';
import 'package:pocketpilot_app/pairing.dart';
import 'package:pocketpilot_app/trust.dart';

const ca = 'ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12';

void main() {
  group('QR code', () {
    test('reads the laptop link', () {
      final p = Pairing.fromQr('https://192.168.1.5:8765/?token=secret&ca=${ca.toUpperCase()}');
      expect(p.host, '192.168.1.5');
      expect(p.port, 8765);
      expect(p.token, 'secret');
      expect(p.caSha256, ca);
      expect(p.pageUrl.toString(), 'https://192.168.1.5:8765/?token=secret');
      expect(p.caUrl.toString(), 'https://192.168.1.5:8765/pocketpilot-ca.crt');
    });

    test('explains what is wrong with other codes', () {
      expect(() => Pairing.fromQr('hello'), throwsA(isA<PairingError>()));
      expect(() => Pairing.fromQr('http://1.2.3.4:8765/?token=t'),
          throwsA(predicate((e) => e.toString().contains('without HTTPS'))));
      expect(() => Pairing.fromQr('https://1.2.3.4:8765/?token=t'),
          throwsA(predicate((e) => e.toString().contains('older PocketPilot'))));
      expect(() => Pairing.fromQr('https://1.2.3.4:8765/?ca=$ca'), throwsA(isA<PairingError>()));
    });

    test('saves and loads the same pairing', () {
      final p = Pairing.fromQr('https://10.0.0.2:9000/?token=t&ca=$ca');
      final back = Pairing.fromJson(jsonDecode(jsonEncode(p.toJson())) as Map<String, dynamic>);
      expect(back.pageUrl, p.pageUrl);
      expect(back.withHost('10.0.0.9', 9001).pageUrl.toString(), 'https://10.0.0.9:9001/?token=t');
    });
  });

  group('discovery', () {
    test('tag matches the laptop (server/discovery.py)', () {
      expect(discoveryTag('secret-token'), '82d6eeae7a4ae3b4');
    });

    test('accepts only answers for this pairing', () {
      List<int> reply(Map<String, Object?> m) => utf8.encode(jsonEncode(m));
      final good = parseReply(reply({'app': 'pocketpilot', 'ip': '10.0.0.7', 'port': 8765, 'ca': ca}), ca);
      expect(good?.host, '10.0.0.7');
      expect(parseReply(reply({'app': 'pocketpilot', 'ip': '10.0.0.7', 'port': 8765, 'ca': 'other'}), ca), isNull);
      expect(parseReply(reply({'app': 'x', 'ip': '10.0.0.7', 'port': 8765, 'ca': ca}), ca), isNull);
      expect(parseReply(reply({'app': 'pocketpilot', 'ip': 'not-an-ip', 'port': 8765, 'ca': ca}), ca), isNull);
      expect(parseReply(utf8.encode('garbage'), ca), isNull);
    });
  });

  group('certificate', () {
    test('PEM to DER and fingerprint', () {
      final der = [1, 2, 3, 4, 250];
      final pem = '-----BEGIN CERTIFICATE-----\n${base64Encode(der)}\n-----END CERTIFICATE-----\n';
      expect(pemToDer(pem), der);
      expect(sha256Hex(der).length, 64);
    });
  });
}
