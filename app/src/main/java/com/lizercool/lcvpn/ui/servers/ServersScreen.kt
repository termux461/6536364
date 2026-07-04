package com.lizercool.lcvpn.ui.servers

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.data.db.entity.ServerEntity

@Composable
fun ServersScreen(viewModel: ServersViewModel = viewModel()) {
    val servers by viewModel.servers.collectAsState()
    val isPinging by viewModel.isPinging.collectAsState()
    var query by remember { mutableStateOf("") }

    val filtered = servers.filter { it.name.contains(query, ignoreCase = true) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Серверы") },
                actions = {
                    IconButton(onClick = { viewModel.refreshPings() }) {
                        if (isPinging) {
                            CircularProgressIndicator(modifier = Modifier.padding(8.dp))
                        } else {
                            Icon(Icons.Filled.Refresh, contentDescription = "Обновить")
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Поиск локации...") },
                modifier = Modifier.fillMaxWidth(),
            )
            LazyColumn(modifier = Modifier.padding(top = 12.dp)) {
                items(filtered, key = { it.id }) { server ->
                    ServerRow(server = server, onClick = { viewModel.select(server) })
                }
            }
        }
    }
}

@Composable
private fun ServerRow(server: ServerEntity, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(14.dp),
    ) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text("${server.countryFlagEmoji} ${server.name}".trim(), style = MaterialTheme.typography.titleMedium)
                Text(server.protocol.label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
            val ping = server.lastPingMs
            Text(
                text = ping?.let { "${it}ms" } ?: "—",
                color = if (ping != null) Color(0xFF22C55E) else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
            )
        }
    }
}
