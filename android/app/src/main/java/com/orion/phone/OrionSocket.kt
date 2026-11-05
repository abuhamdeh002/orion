package com.orion.phone

import android.os.Handler
import android.os.Looper
import java.net.URLEncoder
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/**
 * One relay connection for the whole app, reconnecting with backoff.
 * Replies are matched to requests by frame id; presence frames only update the status line.
 */
object OrionSocket {
    private val client = OkHttpClient.Builder().pingInterval(25, TimeUnit.SECONDS).build()
    private val main = Handler(Looper.getMainLooper())
    private val waiting = ConcurrentHashMap<String, (JSONObject) -> Unit>()
    private val outbox = ArrayDeque<String>()
    private var socket: WebSocket? = null
    private var open = false
    private var retryMs = 1_000L

    /** Called with "online" or "offline" whenever the relay reports the PC's state. */
    var onPresence: ((String) -> Unit)? = null

    @Synchronized
    fun send(frame: String, onReply: (JSONObject) -> Unit) {
        val id = Frames.parse(frame).optString("id")
        if (id.isNotEmpty()) waiting[id] = onReply
        if (open) socket?.send(frame) else {
            outbox.addLast(frame)
            connect()
        }
    }

    @Synchronized
    fun reset() {
        socket?.close(1000, "re-paired")
        socket = null
        open = false
    }

    @Synchronized
    private fun connect() {
        if (socket != null) return
        val prefs = OrionApp.prefs()
        val relay = prefs.getString("relay", null) ?: return failAll("Pair with your PC first.")
        val token = prefs.getString("token", null) ?: return failAll("Pair with your PC first.")
        val account = prefs.getString("account", null) ?: return failAll("Pair with your PC first.")
        val device = prefs.getString("device", null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString("device", it).apply()
        }
        val join = if (relay.contains("?")) "&" else "?"
        val url = relay + join + "account=" + enc(account) + "&role=phone&device=" + enc(device)
        val request = Request.Builder().url(url).header("Authorization", "Bearer $token").build()
        socket = client.newWebSocket(request, Listener())
    }

    private fun enc(value: String) = URLEncoder.encode(value, "UTF-8")

    private fun failAll(message: String) {
        val frame = JSONObject().put("text", message).put("message", message).put("error", true)
        waiting.values.forEach { callback -> callback(frame) }
        waiting.clear()
        outbox.clear()
    }

    private class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            synchronized(OrionSocket) {
                open = true
                retryMs = 1_000L
                webSocket.send(Frames.hello("phone"))
                while (outbox.isNotEmpty()) webSocket.send(outbox.removeFirst())
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val frame = runCatching { Frames.parse(text) }.getOrNull() ?: return
            val id = frame.optString("id")
            when (frame.optString("type")) {
                "presence" -> {
                    val state = frame.optString("text")
                    onPresence?.invoke(state)
                    // The relay answers a request with a presence frame when the PC is not connected.
                    if (id.isNotEmpty()) waiting.remove(id)?.invoke(
                        JSONObject().put("text", "Your PC is offline right now.").put("message", "Your PC is offline right now.").put("error", true),
                    )
                }
                "hello", "token" -> Unit
                else -> if (id.isNotEmpty()) waiting.remove(id)?.invoke(frame)
            }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = dropped(webSocket, code == 4401)

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
            dropped(webSocket, response?.code == 401)

        private fun dropped(webSocket: WebSocket, unauthorised: Boolean) {
            synchronized(OrionSocket) {
                if (socket === webSocket) {
                    socket = null
                    open = false
                }
                if (unauthorised) {
                    failAll("The relay refused this phone. Pair again from the PC.")
                    return
                }
                if (waiting.isEmpty() && outbox.isEmpty()) return
                val delay = retryMs
                retryMs = minOf(retryMs * 2, 60_000L)
                main.postDelayed({ connect() }, delay)
            }
        }
    }
}
