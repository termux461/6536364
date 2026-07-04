package com.lizercool.lcvpn.data.db

import androidx.room.TypeConverter
import com.lizercool.lcvpn.data.model.ProxyProtocol

class Converters {
    @TypeConverter
    fun fromProtocol(value: ProxyProtocol): String = value.name

    @TypeConverter
    fun toProtocol(value: String): ProxyProtocol = ProxyProtocol.valueOf(value)
}
