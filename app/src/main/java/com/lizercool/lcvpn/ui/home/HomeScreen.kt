package com.lizercool.lcvpn.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.weight
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.R
import com.lizercool.lcvpn.util.Formatting
import com.lizercool.lcvpn.vpn.ConnectionState
import com.lizercool.lcvpn.vpn.ProxyStats
import kotlinx.coroutines.delay

@Composable
fun HomeScreen(
    onRequestConnect: () -> Unit,
    onDisconnect: () -> Unit,
    viewModel: HomeViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    val state = uiState.connectionState

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(24.dp))

        val statusText = when (state) {
            is ConnectionState.Connected -> stringResource(R.string.status_protected)
            ConnectionState.Connecting -> "ПОДКЛЮЧЕНИЕ..."
            is ConnectionState.Error -> "ОШИБКА"
            ConnectionState.Disconnected -> stringResource(R.string.status_unprotected)
        }
        Text(statusText, style = MaterialTheme.typography.labelLarge, letterSpacing = 3.sp)
        Text(
            if (state is ConnectionState.Connected) stringResource(R.string.tap_to_disconnect) else stringResource(R.string.tap_to_connect),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        )

        Spacer(Modifier.height(32.dp))

        ConnectCircle(
            connected = state is ConnectionState.Connected,
            connecting = state == ConnectionState.Connecting,
            onClick = {
                if (state is ConnectionState.Connected) onDisconnect() else onRequestConnect()
            },
        )

        Spacer(Modifier.height(24.dp))

        if (state is ConnectionState.Connected) {
            ElapsedTimer(sinceEpochMs = state.sinceEpochMs)
            Spacer(Modifier.height(24.dp))
            SpeedRow(uiState.stats)
        }

        Spacer(Modifier.height(24.dp))

        val server = uiState.selectedServer
        Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text("Авто · быстрейший", style = MaterialTheme.typography.titleMedium)
                    Text(
                        server?.let { "${it.countryFlagEmoji} ${it.name}" } ?: "Сервер не выбран",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                    )
                }
                server?.lastPingMs?.let {
                    Text("${it}ms", color = AccentGreenLocal)
                }
            }
        }
    }
}

@Composable
private fun ConnectCircle(connected: Boolean, connecting: Boolean, onClick: () -> Unit) {
    val ringColor = when {
        connected -> AccentGreenLocal
        connecting -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f)
    }
    Box(
        modifier = Modifier
            .size(220.dp)
            .border(2.dp, ringColor, CircleShape)
            .padding(16.dp)
            .background(ringColor.copy(alpha = 0.08f), CircleShape)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.Filled.PowerSettingsNew,
            contentDescription = null,
            tint = ringColor,
            modifier = Modifier.size(64.dp),
        )
    }
}

@Composable
private fun ElapsedTimer(sinceEpochMs: Long) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(sinceEpochMs) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    Text(
        Formatting.elapsed(sinceEpochMs, now),
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.Bold,
        color = AccentGreenLocal,
    )
}

@Composable
private fun SpeedRow(stats: ProxyStats) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        SpeedTile(
            modifier = Modifier.weight(1f),
            icon = Icons.Filled.ArrowDownward,
            speedText = Formatting.speed(stats.downlinkBytesPerSec),
            label = "ЗАГРУЗКА · ${Formatting.bytes(stats.totalDownlinkBytes)}",
        )
        SpeedTile(
            modifier = Modifier.weight(1f),
            icon = Icons.Filled.ArrowUpward,
            speedText = Formatting.speed(stats.uplinkBytesPerSec),
            label = "ОТДАЧА · ${Formatting.bytes(stats.totalUplinkBytes)}",
        )
    }
}

@Composable
private fun SpeedTile(modifier: Modifier, icon: androidx.compose.ui.graphics.vector.ImageVector, speedText: String, label: String) {
    Card(modifier = modifier, shape = RoundedCornerShape(14.dp)) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = AccentGreenLocal, modifier = Modifier.size(20.dp))
            Column(modifier = Modifier.padding(start = 8.dp)) {
                Text(speedText, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
        }
    }
}

private val AccentGreenLocal = Color(0xFF22C55E)
