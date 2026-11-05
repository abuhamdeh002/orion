package com.orion.phone

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import com.google.android.gms.location.LocationServices

object Sensors {
    fun reportBattery(context: Context) {
        val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return
        val level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val plugged = battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0
        OrionSocket.send(Frames.command("battery", "note", mapOf("text" to "Phone battery $level percent", "plugged" to plugged.toString()))) {}
    }

    fun reportLocation(context: Context) {
        LocationServices.getFusedLocationProviderClient(context).lastLocation.addOnSuccessListener { location ->
            if (location == null) return@addOnSuccessListener
            OrionSocket.send(Frames.chat("where", "I am at ${location.latitude},${location.longitude}")) {}
        }
    }

    fun ring(context: Context) {
        context.sendBroadcast(Intent(context, FindPhoneReceiver::class.java))
    }
}
