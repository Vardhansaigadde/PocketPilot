package io.github.vardhansaigadde.pocketpilot_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayInputStream
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * One native check the Dart side can't do: was the laptop's certificate signed by the
 * laptop's own CA (the one pinned when pairing) and is it in date? Uses Android's
 * java.security, nothing custom.
 */
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "pocketpilot/trust")
            .setMethodCallHandler { call, result ->
                if (call.method != "verify") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val leaf = call.argument<ByteArray>("leaf")
                val ca = call.argument<ByteArray>("ca")
                result.success(leaf != null && ca != null && signedBy(leaf, ca))
            }
    }

    private fun signedBy(leafDer: ByteArray, caDer: ByteArray): Boolean = try {
        val factory = CertificateFactory.getInstance("X.509")
        val leaf = factory.generateCertificate(ByteArrayInputStream(leafDer)) as X509Certificate
        val ca = factory.generateCertificate(ByteArrayInputStream(caDer)) as X509Certificate
        leaf.checkValidity()
        leaf.verify(ca.publicKey)          // throws if not signed by this CA
        true
    } catch (e: Exception) {
        false
    }
}
