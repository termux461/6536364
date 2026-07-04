package com.lizercool.lcvpn.ui.subscriptions

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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SubscriptionsScreen(viewModel: SubscriptionsViewModel = viewModel()) {
    val subscriptions by viewModel.subscriptions.collectAsState()
    val refreshingIds by viewModel.refreshingIds.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Подписки (${subscriptions.size})") }) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Filled.Add, contentDescription = null)
                Text("  Добавить подписку")
            }
        },
    ) { padding ->
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
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), shape = RoundedCornerShape(16.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Column {
                    Text(subscription.name, style = MaterialTheme.typography.titleMedium)
                    if (subscription.isReserve) {
                        Text("РЕЗЕРВНАЯ", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
                    }
                }
            }
            Text(
                subscription.url,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                maxLines = 1,
            )
            Spacer()
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Column {
                    Text("ИСПОЛЬЗОВАНО", style = MaterialTheme.typography.labelSmall)
                    Text(formatBytes(subscription.usedBytes))
                }
                Column {
                    Text("ЛИМИТ", style = MaterialTheme.typography.labelSmall)
                    Text(subscription.limitBytes?.let { formatBytes(it) } ?: "Безлимит")
                }
            }
            Spacer()
            Row(verticalAlignment = Alignment.CenterVertically) {
                subscription.expiresAtEpochMs?.let {
                    Text(formatExpiry(it), style = MaterialTheme.typography.labelSmall)
                    Spacer()
                }
                if (isRefreshing) {
                    CircularProgressIndicator(modifier = Modifier.padding(4.dp))
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
                onClick = { if (url.isNotBlank()) onConfirm(name.ifBlank { "WolfPN" }, url, isReserve) },
            ) { Text("Добавить") }
        },
        dismissButton = {
            androidx.compose.material3.TextButton(onClick = onDismiss) { Text("Отмена") }
        },
    )
}

private fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "0 Б"
    val units = arrayOf("Б", "КБ", "МБ", "ГБ", "ТБ")
    var value = bytes.toDouble()
    var unitIndex = 0
    while (value >= 1024 && unitIndex < units.lastIndex) {
        value /= 1024
        unitIndex++
    }
    return "%.1f %s".format(value, units[unitIndex])
}

private fun formatExpiry(epochMs: Long): String {
    val daysLeft = TimeUnit.MILLISECONDS.toDays(epochMs - System.currentTimeMillis())
    if (daysLeft < 0) return "истекла"
    return "$daysLeft дн."
}
