package com.lizercool.lcvpn.ui.subscriptions

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
import com.lizercool.lcvpn.util.Formatting
import java.util.concurrent.TimeUnit

private val AccentGreen = Color(0xFF22C55E)
private val AccentAmber = Color(0xFFF59E0B)
private val AccentRed = Color(0xFFEF4444)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SubscriptionsScreen(viewModel: SubscriptionsViewModel = viewModel()) {
    val subscriptions by viewModel.subscriptions.collectAsState()
    val refreshingIds by viewModel.refreshingIds.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Подписки · ${subscriptions.size}") }) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Filled.Add, contentDescription = null)
                Text("  Добавить подписку")
            }
        },
    ) { padding ->
        if (subscriptions.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(top = 64.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(
                    Icons.Filled.CloudOff,
                    contentDescription = null,
                    modifier = Modifier.padding(bottom = 12.dp),
                    tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
                )
                Text("Подписок пока нет", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Добавьте ссылку на подписку кнопкой ниже.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                )
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
                items(subscriptions, key = { it.id }) { subscription ->
                    SubscriptionCard(
                        subscription = subscription,
                        isRefreshing = refreshingIds.contains(subscription.id),
                        onRefresh = { viewModel.refresh(subscription) },
                        onDelete = { viewModel.deleteSubscription(subscription) },
                    )
                }
            }
        }
    }

    if (showAddDialog) {
        AddSubscriptionDialog(
            onDismiss = { showAddDialog = false },
            onConfirm = { name, url, isReserve ->
                viewModel.addSubscription(name, url, isReserve)
                showAddDialog = false
            },
        )
    }
}

@Composable
private fun SubscriptionCard(
    subscription: SubscriptionEntity,
    isRefreshing: Boolean,
    onRefresh: () -> Unit,
    onDelete: () -> Unit,
) {
    val clipboard = LocalClipboardManager.current
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Column {
                    Text(subscription.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium)
                    if (subscription.isReserve) {
                        Text("РЕЗЕРВНАЯ", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary, fontWeight = FontWeight.Bold)
                    }
                }
                subscription.expiresAtEpochMs?.let {
                    Text(formatExpiry(it), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            }
            Text(
                subscription.url,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                maxLines = 1,
            )

            val limit = subscription.limitBytes
            Spacer()
            if (limit != null && limit > 0) {
                val fraction = (subscription.usedBytes.toFloat() / limit).coerceIn(0f, 1f)
                val barColor = when {
                    fraction < 0.7f -> AccentGreen
                    fraction < 0.9f -> AccentAmber
                    else -> AccentRed
                }
                LinearProgressIndicator(
                    progress = { fraction },
                    modifier = Modifier.fillMaxWidth().clip(CircleShape),
                    color = barColor,
                    trackColor = barColor.copy(alpha = 0.15f),
                )
                Spacer()
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Text(Formatting.bytes(subscription.usedBytes), style = MaterialTheme.typography.bodySmall)
                    Text("из ${Formatting.bytes(limit)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            } else {
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Column {
                        Text("ИСПОЛЬЗОВАНО", style = MaterialTheme.typography.labelSmall)
                        Text(Formatting.bytes(subscription.usedBytes))
                    }
                    Column {
                        Text("ЛИМИТ", style = MaterialTheme.typography.labelSmall)
                        Text("Безлимит")
                    }
                }
            }
            Spacer()
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (isRefreshing) {
                    CircularProgressIndicator(modifier = Modifier.padding(12.dp).size(20.dp), strokeWidth = 2.dp)
                } else {
                    IconButton(onClick = onRefresh) { Icon(Icons.Filled.Refresh, contentDescription = "Обновить") }
                }
                IconButton(onClick = { clipboard.setText(AnnotatedString(subscription.url)) }) {
                    Icon(Icons.Filled.ContentCopy, contentDescription = "Копировать")
                }
                IconButton(onClick = onDelete) { Icon(Icons.Filled.Delete, contentDescription = "Удалить") }
            }
        }
    }
}

@Composable
private fun Spacer() = androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 6.dp))

@Composable
private fun AddSubscriptionDialog(
    onDismiss: () -> Unit,
    onConfirm: (name: String, url: String, isReserve: Boolean) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var isReserve by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Добавить подписку") },
        text = {
            Column {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Название") })
                OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("Ссылка") })
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                    Switch(checked = isReserve, onCheckedChange = { isReserve = it })
                    Text("  Использовать как резервную")
                }
            }
        },
        confirmButton = {
            androidx.compose.material3.TextButton(
                onClick = { if (url.isNotBlank()) onConfirm(name.ifBlank { "Lizercool" }, url, isReserve) },
            ) { Text("Добавить") }
        },
        dismissButton = {
            androidx.compose.material3.TextButton(onClick = onDismiss) { Text("Отмена") }
        },
    )
}

private fun formatExpiry(epochMs: Long): String {
    val daysLeft = TimeUnit.MILLISECONDS.toDays(epochMs - System.currentTimeMillis())
    if (daysLeft < 0) return "истекла"
    return "$daysLeft дн."
}
