package com.example.acnotification.car

import android.content.Intent
import androidx.car.app.Screen
import androidx.car.app.Session

class AcCarSession : Session() {

    override fun onCreateScreen(intent: Intent): Screen {
        return AcDashboardScreen(carContext)
    }
}
