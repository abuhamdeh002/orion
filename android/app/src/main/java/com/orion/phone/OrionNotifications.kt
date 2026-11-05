package com.orion.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent

object OrionNotifications {
    private val channels = listOf("reminder", "briefing", "battery", "done", "confirm_request", "reply")

    fun ensure(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        channels.forEach { kind ->
            manager.createNotificationChannel(NotificationChannel(kind, kind, NotificationManager.IMPORTANCE_DEFAULT))
        }
    }

    fun show(context: Context, kind: String, text: String) {
        ensure(context)
        val yes = PendingIntent.getBroadcast(context, 1, Intent(context, FindPhoneReceiver::class.java).putExtra("answer", "yes"), PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(context, if (kind in channels) kind else "reply")
            .setContentTitle("ORION")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .addAction(Notification.Action.Builder(null, "Yes", yes).build())
            .build()
        context.getSystemService(NotificationManager::class.java).notify(text.hashCode(), notification)
    }
}
