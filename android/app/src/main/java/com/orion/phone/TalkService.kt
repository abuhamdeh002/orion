package com.orion.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder

class TalkService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("talk", "Talk", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, "talk").setContentTitle("ORION is listening").setSmallIcon(android.R.drawable.ic_btn_speak_now).build()
        startForeground(7, notification)
        return START_NOT_STICKY
    }
}
