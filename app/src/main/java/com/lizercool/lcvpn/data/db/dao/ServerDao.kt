package com.lizercool.lcvpn.data.db.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ServerDao {
    @Query("SELECT * FROM servers ORDER BY id ASC")
    fun observeAll(): Flow<List<ServerEntity>>

    @Query("SELECT * FROM servers WHERE isSelected = 1 LIMIT 1")
    fun observeSelected(): Flow<ServerEntity?>

    @Query("SELECT * FROM servers WHERE subscriptionId = :subscriptionId")
    suspend fun bySubscription(subscriptionId: Long): List<ServerEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(servers: List<ServerEntity>): List<Long>

    @Update
    suspend fun update(server: ServerEntity)

    @Delete
    suspend fun delete(server: ServerEntity)

    @Query("DELETE FROM servers WHERE subscriptionId = :subscriptionId")
    suspend fun deleteBySubscription(subscriptionId: Long)

    @Query("UPDATE servers SET isSelected = 0")
    suspend fun clearSelection()

    @Query("UPDATE servers SET isSelected = 1 WHERE id = :serverId")
    suspend fun select(serverId: Long)

    @Query("UPDATE servers SET lastPingMs = :pingMs WHERE id = :serverId")
    suspend fun updatePing(serverId: Long, pingMs: Int?)
}
