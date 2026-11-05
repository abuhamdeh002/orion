package com.orion.phone

import android.app.Application
import android.content.Context

class OrionApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    companion object {
        lateinit var instance: OrionApp
        fun prefs() = instance.getSharedPreferences("orion", Context.MODE_PRIVATE)
    }
}
