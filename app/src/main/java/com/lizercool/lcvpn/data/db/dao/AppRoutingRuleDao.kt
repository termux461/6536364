package com.lizercool.lcvpn.data.db.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.lizercool.lcvpn.data.db.entity.AppRoutingRuleEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AppRoutingRuleDao {
    @Query("SELECT * FROM app_routing_rules")
    fun observeAll(): Flow<List<AppRoutingRuleEntity>>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(rule: AppRoutingRuleEntity)

    @Delete
    suspend fun delete(rule: AppRoutingRuleEntity)

    @Query("DELETE FROM app_routing_rules")
    suspend fun clear()
}
