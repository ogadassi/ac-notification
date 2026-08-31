package com.example.acnotification.car

import android.content.pm.ApplicationInfo
import androidx.car.app.CarAppService
import androidx.car.app.Session
import androidx.car.app.SessionInfo
import androidx.car.app.validation.HostValidator

class AcCarAppService : CarAppService() {

    override fun createHostValidator(): HostValidator {
        // Allows Android Auto on both vehicle head units and DHU emulator to bind without signature rejection
        return HostValidator.ALLOW_ALL_HOSTS_VALIDATOR
    }

    override fun onCreateSession(sessionInfo: SessionInfo): Session {
        return AcCarSession()
    }
}
