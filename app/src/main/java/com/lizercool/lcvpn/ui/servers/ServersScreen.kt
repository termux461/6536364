package com.lizercool.lcvpn.ui.servers

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.data.db.entity.ServerEntity

private val PingGreen = Color(0xFF22C55E)
private val PingAmber = Color(0xFFF59E0B)
private val PingRed = Color(0xFFEF4444)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ServersScreen(viewModel: ServersViewModel = viewModel()) {
    val servers by viewModel.servers.collectAsState()
    val groups by viewModel.groups.collectAsState()
    val isPinging by viewModel.isPinging.collectAsState()
    var query by remember { mutableStateOf("") }

    // Filter within each group by the search query; drop groups that end up empty.
    val filteredGroups = groups
        .map { g -> g.copy(servers = g.servers.filter { it.name.contains(query, ignoreCase = true) }) }
        .filter { it.servers.isNotEmpty() }
    val multipleGroups = groups.size > 1

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Серверы · ${servers.size}") },
                actions = {
                    IconButton(onClick = { viewModel.refreshPings() }, enabled = !isPinging) {
                        if (isPinging) {
                            CircularProgressIndicator(modifier = Modifier.padding(8.dp).size(20.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Filled.Refresh, contentDescription = "Обновить пинг")
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Поиск локации...") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            if (servers.isEmpty()) {
                EmptyServersState()
            } else {
                LazyColumn(modifier = Modifier.padding(top = 12.dp)) {
                    filteredGroups.forEach { group ->
                        // Only show section headers when there's more than one subscription -
                        // a single-subscription list stays clean and flat.
                        if (multipleGroups) {
                            item(key = "hdr_${group.title}") { GroupHeader(group.title, group.servers.size) }
                        }
                        items(group.servers, key = { it.id }) { server ->
                            ServerRow(server = server, onClick = { viewModel.select(server) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GroupHeader(title: String, count: Int) {
    Text(
        "${title.uppercase()} · $count",
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        modifier = Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 6.dp, start = 4.dp),
    )
}

@Composable
private fun EmptyServersState() {
    Column(
        modifier = Modifier.fillMaxSize().padding(top = 64.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            Icons.Filled.Public,
            contentDescription = null,
            modifier = Modifier.size(48.dp),
            tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
        )
        Text(
            "Серверов пока нет",
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(top = 12.dp),
        )
        Text(
            "Добавьте подписку во вкладке «Подписки», чтобы список серверов заполнился автоматически.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp, start = 32.dp, end = 32.dp),
        )
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
        colors = if (server.isSelected) {
            CardDefaults.cardColors(containerColor = PingGreen.copy(alpha = 0.10f))
        } else {
            CardDefaults.cardColors()
        },
    ) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(server.countryFlagEmoji.ifBlank { "🌐" }, style = MaterialTheme.typography.headlineSmall)
            // weight(1f) lets the name column take the remaining space and ellipsize a long name
            // instead of squeezing the ping badge into a sliver (which was wrapping "224ms" into
            // "22 / 4m / s").
            Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
                Text(
                    server.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                )
                Text(server.protocol.label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
            PingBadge(server.lastPingMs, modifier = Modifier.padding(start = 8.dp))
            if (server.isSelected) {
                Icon(
                    Icons.Filled.CheckCircle,
                    contentDescription = "Выбран",
                    tint = PingGreen,
                    modifier = Modifier.padding(start = 8.dp).size(20.dp),
                )
            }
        }
    }
}

@Composable
private fun PingBadge(pingMs: Int?, modifier: Modifier = Modifier) {
    if (pingMs == null) {
        Text("—", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f), modifier = modifier)
        return
    }
    val color = when {
        pingMs < 120 -> PingGreen
        pingMs < 300 -> PingAmber
        else -> PingRed
    }
    Box(
        modifier = modifier
            .background(color.copy(alpha = 0.12f), CircleShape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(
            "${pingMs}ms",
            color = color,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            softWrap = false,
        )
    }
}
