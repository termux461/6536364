package com.lizercool.lcvpn.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.network.subscription.SubscriptionRepository
import java.util.concurrent.TimeUnit

class SubscriptionRefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val db = AppDatabase.get(applicationContext)
        val repository = SubscriptionRepository(db.subscriptionDao(), db.serverDao())
        repository.refreshAll()
        return Result.success()
    }

    companion object {
        private const val UNIQUE_WORK_NAME = "subscription_refresh"

        fun schedulePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<SubscriptionRefreshWorker>(6, TimeUnit.HOURS).build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(UNIQUE_WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
