package com.lizercool.lcvpn.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.lizercool.lcvpn.data.db.dao.AppRoutingRuleDao
import com.lizercool.lcvpn.data.db.dao.ServerDao
import com.lizercool.lcvpn.data.db.dao.SubscriptionDao
import com.lizercool.lcvpn.data.db.entity.AppRoutingRuleEntity
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity

@Database(
    entities = [ServerEntity::class, SubscriptionEntity::class, AppRoutingRuleEntity::class],
    version = 2,
    exportSchema = false,
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun serverDao(): ServerDao
    abstract fun subscriptionDao(): SubscriptionDao
    abstract fun appRoutingRuleDao(): AppRoutingRuleDao

    companion object {
        @Volatile private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                AppDatabase::class.java,
                "lcvpn.db",
            ).fallbackToDestructiveMigration().build().also { instance = it }
        }
    }
}
