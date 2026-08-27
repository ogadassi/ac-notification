package com.example.acnotification.car

import android.content.pm.ApplicationInfo
import androidx.car.app.CarAppService
import androidx.car.app.Session
import androidx.car.app.SessionInfo
import androidx.car.app.validation.HostValidator

class AcCarAppService : CarAppService() {

    override fun createHostValidator(): HostValidator {
        return if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
            // Allows testing with Desktop Head Unit (DHU) emulator during development
            HostValidator.ALLOW_ALL_HOSTS_VALIDATOR
        } else {
            // In release, validate against official Android Auto package signatures
            HostValidator.Builder(applicationContext)
                .addAllowedHosts(androidx.car.app.R.array.hosts_allowlist_sample)
                .build()
        }
    }

    override fun onCreateSession(sessionInfo: SessionInfo): Session {
        return AcCarSession()
    }
}
