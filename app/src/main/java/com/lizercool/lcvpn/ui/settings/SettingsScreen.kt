package com.lizercool.lcvpn.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.BuildConfig
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode

private val tabTitles = listOf("Общие", "Подключение", "Маршрутизация", "Анти-DPI", "О прил.")

@Composable
fun SettingsScreen(viewModel: SettingsViewModel = viewModel()) {
    var selectedTab by remember { mutableIntStateOf(0) }

    Scaffold(topBar = { TopAppBar(title = { Text("Настройки") }) }) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = selectedTab) {
                tabTitles.forEachIndexed { index, title ->
                    Tab(selected = selectedTab == index, onClick = { selectedTab = index }, text = { Text(title) })
                }
            }
            when (selectedTab) {
                0 -> GeneralTab(viewModel)
                1 -> ConnectionTab(viewModel)
                2 -> RoutingTab()
                3 -> AntiDpiTab()
                4 -> AboutTab(viewModel)
            }
        }
    }
}

@Composable
private fun GeneralTab(viewModel: SettingsViewModel) {
    val language by viewModel.language.collectAsState()
    val darkTheme by viewModel.darkTheme.collectAsState()
    val sortOrder by viewModel.sortOrder.collectAsState()
    val connectOnLaunch by viewModel.connectOnLaunch.collectAsState()
    val updateOnLaunch by viewModel.updateOnLaunch.collectAsState()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SectionLabel("ЯЗЫК")
        SegmentedRow(
            options = listOf("ru" to "Русский", "en" to "English"),
            selected = language,
            onSelect = viewModel::setLanguage,
        )

        SectionLabel("ТЕМА")
        SegmentedRow(
            options = listOf(true to "Тёмная", false to "Светлая"),
            selected = darkTheme,
            onSelect = viewModel::setDarkTheme,
        )

        SectionLabel("СПИСОК СЕРВЕРОВ")
        SegmentedRow(
            options = listOf(
                ServerListSort.NONE to "Без сортировки",
                ServerListSort.PING to "По пингу",
                ServerListSort.ALPHABETICAL to "По алфавиту",
            ),
            selected = sortOrder,
            onSelect = viewModel::setSortOrder,
        )

        SectionLabel("ПОВЕДЕНИЕ ПРИ ЗАПУСКЕ")
        SwitchRow("Подключаться при запуске", connectOnLaunch, viewModel::setConnectOnLaunch)
        SwitchRow("Обновлять при открытии", updateOnLaunch, viewModel::setUpdateOnLaunch)
    }
}

@Composable
private fun ConnectionTab(viewModel: SettingsViewModel) {
    val tunnelMode by viewModel.tunnelMode.collectAsState()
    val appRoutingMode by viewModel.appRoutingMode.collectAsState()
    val selectedPackages by viewModel.selectedPackages.collectAsState()
    var query by remember { mutableStateOf("") }

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        item {
            SectionLabel("РЕЖИМ ТУННЕЛЯ")
            SegmentedRow(
                options = listOf(TunnelMode.PROXY to "Прокси", TunnelMode.TUN to "TUN (полный VPN)"),
                selected = tunnelMode,
                onSelect = viewModel::setTunnelMode,
            )

            SectionLabel("ЧТО ПУСКАТЬ ЧЕРЕЗ VPN")
            SegmentedRow(
                options = listOf(
                    AppRoutingMode.ALL_EXCEPT_SELECTED to "Все, кроме выбранных",
                    AppRoutingMode.ONLY_SELECTED to "Только выбранные",
                ),
                selected = appRoutingMode,
                onSelect = viewModel::setAppRoutingMode,
            )

            SectionLabel("ПРИЛОЖЕНИЯ · ${selectedPackages.size}")
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Поиск приложения...") },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        val filteredApps = viewModel.installedApps.filter { it.label.contains(query, ignoreCase = true) }
        items(filteredApps, key = { it.packageName }) { app ->
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(app.label, modifier = Modifier.fillMaxWidth(0.8f))
                Switch(
                    checked = selectedPackages.contains(app.packageName),
                    onCheckedChange = { viewModel.toggleAppSelected(app.packageName, it) },
                )
            }
        }
    }
}

@Composable
private fun RoutingTab() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SectionLabel("ПРАВИЛА МАРШРУТИЗАЦИИ")
        Text(
            "Домены и приложения, которые должны идти в обход VPN, настраиваются здесь. " +
                "Эта часть UI - следующий шаг после того как заработает базовое подключение.",
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun AntiDpiTab() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SectionLabel("АНТИ-DPI")
        Text(
            "Настройки обфускации (фрагментация TLS ClientHello, паддинг пакетов и т.п.) " +
                "будут выведены сюда, когда основной движок подключения будет готов.",
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun AboutTab(viewModel: SettingsViewModel) {
    val context = LocalContext.current
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Lizercool (LC VPN)", style = MaterialTheme.typography.titleLarge)
        Text("Версия ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyMedium)

        SectionLabel("ПОДДЕРЖКА")
        Button(onClick = {
            val intent = viewModel.shareLogsIntent()
            if (intent != null) context.startActivity(intent)
        }) {
            Text("Поделиться логами")
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        modifier = Modifier.padding(top = 16.dp, bottom = 8.dp),
    )
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.fillMaxWidth(0.8f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun <T> SegmentedRow(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth()) {
        options.forEach { (value, label) ->
            val isSelected = value == selected
            Button(
                onClick = { onSelect(value) },
                modifier = Modifier.fillMaxWidth(1f / options.size).padding(2.dp),
                colors = if (isSelected) {
                    androidx.compose.material3.ButtonDefaults.buttonColors()
                } else {
                    androidx.compose.material3.ButtonDefaults.outlinedButtonColors()
                },
            ) { Text(label) }
        }
    }
}
