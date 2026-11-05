package com.orion.phone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.VibrationEffect
import android.os.Vibrator
import android.telephony.SmsMessage
import android.telephony.TelephonyManager

class CallSmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val line = when (intent.action) {
            TelephonyManager.ACTION_PHONE_STATE_CHANGED -> {
                val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE)
                val number = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)
                if (state == TelephonyManager.EXTRA_STATE_RINGING) "Incoming call from ${number ?: "unknown"}" else return
            }
            "android.provider.Telephony.SMS_RECEIVED" -> {
                val bundle = intent.extras ?: return
                val pdus = bundle.get("pdus") as? Array<*> ?: return
                val message = SmsMessage.createFromPdu(pdus.first() as ByteArray)
                "SMS from ${message.displayOriginatingAddress}"
            }
            else -> return
        }
        OrionSocket.send(Frames.chat("phone-event", line)) {}
    }
}

class FindPhoneReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val vibrator = context.getSystemService(Vibrator::class.java)
        vibrator.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 400, 200, 400, 200, 800), -1))
    }
}
