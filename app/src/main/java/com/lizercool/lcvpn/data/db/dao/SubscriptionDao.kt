package com.lizercool.lcvpn.data.db.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface SubscriptionDao {
    @Query("SELECT * FROM subscriptions ORDER BY id ASC")
    fun observeAll(): Flow<List<SubscriptionEntity>>

    @Query("SELECT * FROM subscriptions WHERE id = :id")
    suspend fun byId(id: Long): SubscriptionEntity?

    @Query("SELECT * FROM subscriptions WHERE isReserve = 0")
    suspend fun primaries(): List<SubscriptionEntity>

    @Query("SELECT * FROM subscriptions WHERE isReserve = 1")
    suspend fun reserves(): List<SubscriptionEntity>

    @Insert
    suspend fun insert(subscription: SubscriptionEntity): Long

    @Update
    suspend fun update(subscription: SubscriptionEntity)

    @Delete
    suspend fun delete(subscription: SubscriptionEntity)
}
