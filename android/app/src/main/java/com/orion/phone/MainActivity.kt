package com.orion.phone

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    private var status by mutableStateOf("Not paired")
    private var presence by mutableStateOf("")
    private var reply by mutableStateOf("")
    private var draft by mutableStateOf("")
    private var pin by mutableStateOf("")
    private var screen by mutableStateOf("talk")

    private val speech = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val said = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
        if (said.isNotBlank()) sendChat(said)
    }

    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (granted[Manifest.permission.RECORD_AUDIO] == true) holdToTalk()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handlePairing(intent)
        OrionSocket.onPresence = { state -> runOnUiThread { presence = if (state == "online") "PC online" else "PC offline" } }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !granted(Manifest.permission.POST_NOTIFICATIONS)) {
            permissions.launch(arrayOf(Manifest.permission.POST_NOTIFICATIONS))
        }
        setContent {
            MaterialTheme {
                Column(Modifier.fillMaxSize().padding(24.dp)) {
                    Text(status)
                    if (presence.isNotEmpty()) Text(presence)
                    Text(reply)
                    if (screen == "talk") {
                        Button(onClick = { holdToTalk() }) { Text("Hold to talk") }
                        TextField(value = draft, onValueChange = { draft = it }, label = { Text("Or type") })
                        Button(onClick = { sendChat(draft) }) { Text("Send") }
                        Button(onClick = { screen = "control" }) { Text("Control the PC") }
                    } else {
                        listOf("lock", "sleep", "screenshot", "apps").forEach { action ->
                            Button(onClick = { sendCommand(action) }) { Text(action) }
                        }
                        TextField(
                            value = pin,
                            onValueChange = { pin = it.filter(Char::isDigit).take(12) },
                            label = { Text("PIN for shutdown") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        )
                        Button(onClick = { shutdown() }, enabled = pin.length >= 4) { Text("Shut down") }
                        Button(onClick = { screen = "talk" }) { Text("Back") }
                    }
                }
            }
        }
        refresh()
    }

    // A pairing link can arrive while the app is already open (scanning the QR again).
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handlePairing(intent)
    }

    private fun handlePairing(intent: Intent?) {
        val link = intent?.data?.toString() ?: return
        val pairing = Frames.pairFromLink(link)
        if (pairing == null) {
            status = "That pairing link is incomplete. Pair again from the PC."
            return
        }
        save(pairing)
    }

    private fun save(pairing: Pairing) {
        OrionApp.prefs().edit().putString("relay", pairing.relay).putString("account", pairing.account).putString("token", pairing.token).apply()
        OrionSocket.reset()
        refresh()
    }

    private fun refresh() {
        val token = OrionApp.prefs().getString("token", null)
        status = if (token == null) "Scan the QR on the PC." else "Paired."
    }

    private fun granted(permission: String) =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun holdToTalk() {
        if (!granted(Manifest.permission.RECORD_AUDIO)) {
            permissions.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
            return
        }
        speech.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM))
    }

    private fun sendChat(text: String) {
        if (text.isBlank()) return
        reply = "Sending…"
        draft = ""
        OrionSocket.send(Frames.chat(System.currentTimeMillis().toString(), text)) { frame -> show(frame.optString("text")) }
    }

    private fun sendCommand(action: String, arguments: Map<String, String> = emptyMap()) {
        OrionSocket.send(Frames.command(System.currentTimeMillis().toString(), action, arguments)) { frame: JSONObject ->
            show(frame.optString("message").ifEmpty { frame.optString("text") })
        }
    }

    private fun shutdown() {
        sendCommand("shutdown", mapOf("pin" to pin))
        pin = ""
    }

    private fun show(text: String) {
        runOnUiThread { reply = text }
        OrionApp.prefs().edit().putString("last_reply", text).apply()
        OrionWidget.refresh(applicationContext)
    }
}
