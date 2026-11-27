/// Finds the laptop again when its Wi-Fi address changes.
///
/// Sends a UDP broadcast `POCKETPILOT? <tag>` (port 8766). The tag is made from the
/// pairing token, so the token itself never goes over the air, and the laptop only
/// answers phones that know it (server/discovery.py on the laptop).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

const discoveryPort = 8766;
const _ask = 'POCKETPILOT? ';

/// Must match server/discovery.py `tag()`.
String discoveryTag(String token) =>
    sha256.convert(utf8.encode('pocketpilot-discovery:$token')).toString().substring(0, 16);

class Found {
  const Found(this.host, this.port);
  final String host;
  final int port;
}

/// A laptop's answer, or null if it isn't a valid answer for this pairing.
/// The certificate fingerprint must match too: an answer from another machine is ignored.
Found? parseReply(List<int> data, String expectedCaSha256) {
  try {
    final j = jsonDecode(utf8.decode(data)) as Map<String, dynamic>;
    if (j['app'] != 'pocketpilot' || j['ca'] != expectedCaSha256) return null;
    final host = j['ip'] as String;
    final port = j['port'] as int;
    if (InternetAddress.tryParse(host) == null || port <= 0 || port > 65535) return null;
    return Found(host, port);
  } catch (_) {
    return null;
  }
}

/// Asks the Wi-Fi where the laptop is. Null if nothing answers in time.
Future<Found?> discover(String token, String caSha256, {Duration timeout = const Duration(seconds: 3)}) async {
  final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
  socket.broadcastEnabled = true;
  final result = Completer<Found?>();
  final sub = socket.listen((event) {
    if (event != RawSocketEvent.read) return;
    final dg = socket.receive();
    if (dg == null) return;
    final found = parseReply(dg.data, caSha256);
    if (found != null && !result.isCompleted) result.complete(found);
  });
  final ask = utf8.encode('$_ask${discoveryTag(token)}');
  for (var i = 0; i < 3 && !result.isCompleted; i++) {        // UDP can drop a packet: ask 3 times
    socket.send(ask, InternetAddress('255.255.255.255'), discoveryPort);
    await Future.any([result.future, Future.delayed(timeout ~/ 3)]);
  }
  final found = result.isCompleted ? await result.future : null;
  await sub.cancel();
  socket.close();
  return found;
}
