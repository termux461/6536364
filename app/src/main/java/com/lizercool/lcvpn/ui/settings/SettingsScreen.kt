package com.lizercool.lcvpn.ui.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.BuildConfig
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.IpStackMode
import com.lizercool.lcvpn.data.model.PingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode

private val tabTitles = listOf("Общие", "Подключение", "Маршрутизация", "Анти-DPI", "О прил.")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: SettingsViewModel = viewModel()) {
    var selectedTab by remember { mutableIntStateOf(0) }
    var showAppRouting by remember { mutableStateOf(false) }
    var showAdvanced by remember { mutableStateOf(false) }

    if (showAppRouting) {
        AppRoutingScreen(viewModel = viewModel, onBack = { showAppRouting = false })
        return
    }
    if (showAdvanced) {
        AdvancedSettingsScreen(viewModel = viewModel, onBack = { showAdvanced = false })
        return
    }

    Scaffold(topBar = { TopAppBar(title = { Text("Настройки") }) }) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            ScrollableTabRow(selectedTabIndex = selectedTab, edgePadding = 12.dp) {
                tabTitles.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title, maxLines = 1, softWrap = false) },
                    )
                }
            }
            when (selectedTab) {
                0 -> GeneralTab(viewModel)
                1 -> ConnectionTab(
                    viewModel,
                    onOpenAppRouting = { showAppRouting = true },
                    onOpenAdvanced = { showAdvanced = true },
                )
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

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            SettingsCard("ЯЗЫК") {
                SegmentedRow(
                    options = listOf("ru" to "Русский", "en" to "English"),
                    selected = language,
                    onSelect = viewModel::setLanguage,
                )
            }
        }
        item {
            SettingsCard("ТЕМА") {
                SegmentedRow(
                    options = listOf(true to "Тёмная", false to "Светлая"),
                    selected = darkTheme,
                    onSelect = viewModel::setDarkTheme,
                )
            }
        }
        item {
            SettingsCard("СПИСОК СЕРВЕРОВ") {
                SegmentedRow(
                    options = listOf(
                        ServerListSort.NONE to "Обычный",
                        ServerListSort.PING to "Пинг",
                        ServerListSort.ALPHABETICAL to "А–Я",
                    ),
                    selected = sortOrder,
                    onSelect = viewModel::setSortOrder,
                )
            }
        }
        item {
            SettingsCard("ПОВЕДЕНИЕ ПРИ ЗАПУСКЕ") {
                SwitchRow("Подключаться при запуске", connectOnLaunch, viewModel::setConnectOnLaunch)
                SwitchRow("Обновлять при открытии", updateOnLaunch, viewModel::setUpdateOnLaunch)
            }
        }
    }
}

@Composable
private fun ConnectionTab(viewModel: SettingsViewModel, onOpenAppRouting: () -> Unit, onOpenAdvanced: () -> Unit) {
    val tunnelMode by viewModel.tunnelMode.collectAsState()
    val appRoutingMode by viewModel.appRoutingMode.collectAsState()
    val selectedPackages by viewModel.selectedPackages.collectAsState()
    val lanProxyPassword by viewModel.lanProxyPassword.collectAsState()
    val killSwitch by viewModel.killSwitch.collectAsState()
    val ipStackMode by viewModel.ipStackMode.collectAsState()

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            SettingsCard("РЕЖИМ ТУННЕЛЯ") {
                SegmentedRow(
                    options = listOf(
                        TunnelMode.PROXY to "Прокси",
                        TunnelMode.TUN to "TUN",
                        TunnelMode.TUN_AND_PROXY to "TUN+прокси",
                    ),
                    selected = tunnelMode,
                    onSelect = viewModel::setTunnelMode,
                )
                HintText(
                    when (tunnelMode) {
                        TunnelMode.PROXY -> "Локальный SOCKS-прокси. Трафик идёт только из приложений, которые сами умеют в прокси."
                        TunnelMode.TUN -> "Полный VPN — весь трафик устройства идёт через сервер."
                        TunnelMode.TUN_AND_PROXY -> "Полный VPN + прокси в локальной сети для других устройств."
                    },
                )
                if (tunnelMode == TunnelMode.TUN_AND_PROXY) {
                    HintText(
                        "Полный VPN на все приложения + SOCKS5-прокси в локальной сети, " +
                            "чтобы этим же подключением мог пользоваться другой телефон/ПК на том же Wi-Fi.\n\n" +
                            "Адрес: ${viewModel.lanProxyAddress}\n" +
                            "Логин: lcvpn\n" +
                            "Пароль: $lanProxyPassword",
                    )
                }
            }
        }
        if (tunnelMode != TunnelMode.PROXY) {
            item {
                SettingsCard("IP-СТЕК") {
                    SegmentedRow(
                        options = listOf(
                            IpStackMode.BOTH to "IPv4+IPv6",
                            IpStackMode.IPV4_ONLY to "IPv4",
                            IpStackMode.IPV6_ONLY to "IPv6",
                        ),
                        selected = ipStackMode,
                        onSelect = viewModel::setIpStackMode,
                    )
                    HintText(
                        when (ipStackMode) {
                            IpStackMode.BOTH -> "Через VPN идёт и IPv4, и IPv6 (рекомендуется — ничего не утекает мимо туннеля)."
                            IpStackMode.IPV4_ONLY -> "Через VPN идёт только IPv4. IPv6-трафик пойдёт напрямую, мимо VPN."
                            IpStackMode.IPV6_ONLY -> "Через VPN идёт только IPv6. Нужно редко."
                        },
                    )
                }
            }
        }
        item {
            SettingsCard("БЕЗОПАСНОСТЬ") {
                SwitchRow("Kill Switch", killSwitch, viewModel::setKillSwitch)
                if (killSwitch) {
                    HintText(
                        "Если соединение с сервером обрывается в режиме TUN, трафик остаётся " +
                            "заблокированным (не уходит напрямую в интернет), пока приложение само " +
                            "не переподключится.",
                    )
                }
            }
        }
        item {
            val pingMode by viewModel.pingMode.collectAsState()
            SettingsCard("ПРОВЕРКА ПИНГА") {
                OptionColumn(
                    options = listOf(
                        Triple(PingMode.PROXY_GET, "Через прокси (GET)", "Реальное подключение через сервер + HTTP GET. Самый точный, медленнее"),
                        Triple(PingMode.PROXY_HEAD, "Через прокси (HEAD)", "Реальное подключение через сервер + HTTP HEAD. Точный, чуть легче GET"),
                        Triple(PingMode.TCP, "TCP", "Прямое TCP-соединение до сервера. Быстрый, но REALITY-серверы могут не отвечать"),
                        Triple(PingMode.ICMP, "ICMP", "Обычный ping до адреса сервера. Быстрый, вне туннеля"),
                    ),
                    selected = pingMode,
                    onSelect = viewModel::setPingMode,
                )
            }
        }
        item {
            SettingsCard("ЧТО ПУСКАТЬ ЧЕРЕЗ VPN") {
                SegmentedRow(
                    options = listOf(
                        AppRoutingMode.ALL_EXCEPT_SELECTED to "Кроме выбранных",
                        AppRoutingMode.ONLY_SELECTED to "Только выбранные",
                    ),
                    selected = appRoutingMode,
                    onSelect = viewModel::setAppRoutingMode,
                )
                AppRoutingSummaryRow(count = selectedPackages.size, onClick = onOpenAppRouting)
            }
        }
        item {
            SettingsCard("ПРОИЗВОДИТЕЛЬНОСТЬ") {
                NavRow(
                    icon = Icons.Filled.Tune,
                    title = "Расширенные настройки",
                    subtitle = "Sniffing, таймауты, UDP, wakelock, логи",
                    onClick = onOpenAdvanced,
                )
            }
        }
    }
}

/** Generic tappable row with a leading icon, two lines of text and a trailing chevron. */
@Composable
private fun NavRow(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        }
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
    }
}

@Composable
private fun AppRoutingSummaryRow(count: Int, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 12.dp)
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Filled.Apps, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
            Text("Приложения", style = MaterialTheme.typography.bodyLarge)
            Text(
                if (count == 0) "Не выбрано ни одного" else "Выбрано: $count",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            )
        }
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppRoutingScreen(viewModel: SettingsViewModel, onBack: () -> Unit) {
    val installedApps by viewModel.installedApps.collectAsState()
    val isLoading by viewModel.installedAppsLoading.collectAsState()
    val selectedPackages by viewModel.selectedPackages.collectAsState()
    var query by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Приложения") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Назад") }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Поиск приложения...") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            if (isLoading) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(top = 64.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    CircularProgressIndicator()
                    Text(
                        "Загружаем список приложений...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }
            } else {
                val filteredApps = installedApps.filter { it.label.contains(query, ignoreCase = true) }
                LazyColumn(modifier = Modifier.padding(top = 8.dp)) {
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
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AdvancedSettingsScreen(viewModel: SettingsViewModel, onBack: () -> Unit) {
    val sniffing by viewModel.sniffing.collectAsState()
    val idleTimeout by viewModel.idleTimeoutSec.collectAsState()
    val blockUdp by viewModel.blockUdp.collectAsState()
    val keepAwake by viewModel.keepAwake.collectAsState()
    val logRetention by viewModel.logRetentionHours.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Расширенные настройки") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Назад") }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                SettingsCard("СОЕДИНЕНИЯ") {
                    StepperRow(
                        title = "Таймаут простоя",
                        subtitle = "Секунд до закрытия неактивного соединения",
                        value = idleTimeout,
                        step = 30,
                        range = 30..3600,
                        onChange = viewModel::setIdleTimeoutSec,
                    )
                    HorizontalDivider(Modifier.padding(vertical = 4.dp))
                    SwitchRow("Блокировать UDP", blockUdp, viewModel::setBlockUdp)
                    HintText(
                        "Ломает QUIC, DNS-over-UDP, голосовые звонки и игры. Включайте только если " +
                            "знаете зачем (не применяется к конфигам «Автовыбор»).",
                    )
                }
            }
            item {
                SettingsCard("СЕТЬ") {
                    SwitchRow("Анализ трафика (Sniffing)", sniffing, viewModel::setSniffing)
                    HintText(
                        "Определяет домен из TLS/HTTP/QUIC, чтобы работали правила маршрутизации " +
                            "(обход .ru, блок рекламы, балансировщик «Автовыбора»). Рекомендуется включённым.",
                    )
                }
            }
            item {
                SettingsCard("ПИТАНИЕ") {
                    SwitchRow("Держать устройство активным", keepAwake, viewModel::setKeepAwake)
                    HintText(
                        "Удерживает wakelock во время работы VPN. Нужно на Xiaomi/HyperOS; на других " +
                            "устройствах может немного сильнее расходовать батарею.",
                    )
                }
            }
            item {
                SettingsCard("ОТЛАДКА") {
                    Text(
                        "Хранение логов",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                    SegmentedRow(
                        options = listOf(
                            1 to "1 ч",
                            6 to "6 ч",
                            24 to "24 ч",
                            168 to "7 дн",
                            0 to "Всегда",
                        ),
                        selected = logRetention,
                        onSelect = viewModel::setLogRetentionHours,
                    )
                    HintText("Старые логи удаляются при запуске приложения. «Всегда» — не удалять.")
                }
            }
        }
    }
}

/** A label + subtitle with −/value/+ stepper controls on the right. */
@Composable
private fun StepperRow(title: String, subtitle: String, value: Int, step: Int, range: IntRange, onChange: (Int) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        }
        IconButton(onClick = { onChange((value - step).coerceIn(range)) }) {
            Icon(Icons.Filled.Remove, contentDescription = "Меньше")
        }
        Text("$value", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        IconButton(onClick = { onChange((value + step).coerceIn(range)) }) {
            Icon(Icons.Filled.Add, contentDescription = "Больше")
        }
    }
}

@Composable
private fun RoutingTab() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SettingsCard("ПРАВИЛА МАРШРУТИЗАЦИИ") {
            Text(
                "Домены и приложения, которые должны идти в обход VPN, настраиваются здесь. " +
                    "Эта часть UI - следующий шаг после того как заработает базовое подключение.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun AntiDpiTab() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SettingsCard("АНТИ-DPI") {
            Text(
                "Настройки обфускации (фрагментация TLS ClientHello, паддинг пакетов и т.п.) " +
                    "будут выведены сюда, когда основной движок подключения будет готов.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun AboutTab(viewModel: SettingsViewModel) {
    val context = LocalContext.current
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Lizercool (LC VPN)", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(
            "Версия ${BuildConfig.VERSION_NAME}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        )

        SettingsCard("ПОДДЕРЖКА", modifier = Modifier.padding(top = 16.dp)) {
            Button(onClick = {
                val intent = viewModel.shareLogsIntent()
                if (intent != null) context.startActivity(intent)
            }) {
                Text("Поделиться логами")
            }
        }
    }
}

@Composable
private fun SettingsCard(title: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            content()
        }
    }
}

@Composable
private fun HintText(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        modifier = Modifier.padding(top = 8.dp),
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

/** Vertical radio-style list for settings with too many (or too wordy) options for a SegmentedRow. */
@Composable
private fun <T> OptionColumn(options: List<Triple<T, String, String>>, selected: T, onSelect: (T) -> Unit) {
    Column {
        options.forEach { (value, title, subtitle) ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { onSelect(value) }
                    .padding(vertical = 10.dp, horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = value == selected, onClick = { onSelect(value) })
                Column(modifier = Modifier.padding(start = 8.dp)) {
                    Text(title, style = MaterialTheme.typography.bodyLarge)
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> SegmentedRow(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    // Material3's segmented button keeps each label on one line and sizes the segments evenly,
    // instead of the old fixed-width Buttons that broke long labels mid-word ("Без сортиров ки").
    SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
        options.forEachIndexed { index, (value, label) ->
            SegmentedButton(
                selected = value == selected,
                onClick = { onSelect(value) },
                shape = SegmentedButtonDefaults.itemShape(index, options.size),
            ) {
                Text(label, maxLines = 1, softWrap = false, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}
