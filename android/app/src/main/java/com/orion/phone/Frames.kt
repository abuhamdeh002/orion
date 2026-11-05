package com.orion.phone

import java.net.URLDecoder
import org.json.JSONObject

object Frames {
    fun chat(id: String, text: String): String = JSONObject().put("type", "chat").put("id", id).put("text", text).toString()

    fun command(id: String, action: String, arguments: Map<String, String> = emptyMap()): String {
        val args = JSONObject()
        arguments.forEach { (key, value) -> args.put(key, value) }
        return JSONObject().put("type", "do").put("id", id).put("action", action).put("arguments", args).toString()
    }

    fun hello(role: String): String = JSONObject().put("type", "hello").put("role", role).toString()

    fun parse(raw: String): JSONObject = JSONObject(raw)

    /** orion://pair?relay=...&account=...&token=... as made by the PC's POST /pair. All three are required. */
    fun pairFromLink(link: String): Pairing? {
        if (!link.startsWith("orion://pair")) return null
        val query = link.substringAfter("?", "")
        val parts = query.split("&").mapNotNull {
            val bits = it.split("=", limit = 2)
            if (bits.size == 2) bits[0] to URLDecoder.decode(bits[1], "UTF-8") else null
        }.toMap()
        val token = parts["token"]?.takeIf { it.isNotBlank() } ?: return null
        val account = parts["account"]?.takeIf { it.isNotBlank() } ?: return null
        val relay = parts["relay"]?.takeIf { it.startsWith("wss://") || it.startsWith("ws://") } ?: return null
        return Pairing(relay, account, token)
    }
}

data class Pairing(val relay: String, val account: String, val token: String)
