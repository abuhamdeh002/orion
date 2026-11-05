package com.orion.phone

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.widget.RemoteViews

class OrionWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val reply = context.getSharedPreferences("orion", Context.MODE_PRIVATE).getString("last_reply", "Hold to talk")
        ids.forEach { id ->
            val views = RemoteViews(context.packageName, R.layout.widget)
            views.setTextViewText(R.id.presence, "ORION")
            views.setTextViewText(R.id.last_reply, reply)
            manager.updateAppWidget(id, views)
        }
    }

    companion object {
        /** Redraw every placed widget with the latest reply. */
        fun refresh(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, OrionWidget::class.java))
            if (ids.isNotEmpty()) OrionWidget().onUpdate(context, manager, ids)
        }
    }
}
