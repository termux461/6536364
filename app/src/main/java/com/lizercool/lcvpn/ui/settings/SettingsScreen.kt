package com.lizercool.lcvpn.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Terminal
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lizercool.lcvpn.BuildConfig
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.IpStackMode
import com.lizercool.lcvpn.data.model.PingMode
import com.lizercool.lcvpn.data.model.RoutingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode

private val tabTitles = listOf("Общие", "Подключение", "Маршрутизация", "Анти-DPI", "О прил.")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: SettingsViewModel = viewModel()) {
    var selectedTab by remember { mutableIntStateOf(0) }
    var showAppRouting by remember { mutableStateOf(false) }
    var showAdvanced by remember { mutableStateOf(false) }
    var showLogs by remember { mutableStateOf(false) }

    if (showAppRouting) {
        AppRoutingScreen(viewModel = viewModel, onBack = { showAppRouting = false })
        return
    }
    if (showAdvanced) {
        AdvancedSettingsScreen(viewModel = viewModel, onBack = { showAdvanced = false })
        return
    }
    if (showLogs) {
        LogViewerScreen(viewModel = viewModel, onBack = { showLogs = false })
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
                2 -> RoutingTab(viewModel)
                3 -> AntiDpiTab(viewModel)
                4 -> AboutTab(viewModel, onOpenLogs = { showLogs = true })
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
                        "Полный VPN на все приложения + SOCKS5-прокси в локальной сети, чтобы этим же " +
                            "подключением мог пользоваться другой телефон/ПК на том же Wi-Fi.",
                    )
                    CopyRow(label = "Адрес", value = viewModel.lanProxyAddress)
                    CopyRow(label = "Логин", value = "lcvpn")
                    CopyRow(label = "Пароль", value = lanProxyPassword)
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
                val memoryLimit by viewModel.memoryLimitMb.collectAsState()
                val memoryUnlimited by viewModel.memoryUnlimited.collectAsState()
                SettingsCard("ПАМЯТЬ") {
                    Text(
                        "Предел памяти ядра" + if (memoryUnlimited) " (снят)" else ": $memoryLimit МБ",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                    if (!memoryUnlimited) {
                        SegmentedRow(
                            options = listOf(40 to "40", 60 to "60", 80 to "80", 100 to "100", 150 to "150"),
                            selected = memoryLimit,
                            onSelect = viewModel::setMemoryLimitMb,
                        )
                    }
                    SwitchRow("Снять ограничение", memoryUnlimited, viewModel::setMemoryUnlimited)
                    HintText(
                        "Ограничивает память Xray-ядра (GOMEMLIMIT). Меньше — экономнее, больше — " +
                            "стабильнее под нагрузкой. Применяется после перезапуска приложения.",
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
private fun RoutingTab(viewModel: SettingsViewModel) {
    val routingMode by viewModel.routingMode.collectAsState()
    val directDomains by viewModel.directDomains.collectAsState()
    val proxyDomains by viewModel.proxyDomains.collectAsState()

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            SettingsCard("РЕЖИМ") {
                SegmentedRow(
                    options = listOf(
                        RoutingMode.SMART to "Умный",
                        RoutingMode.GLOBAL to "Всё через VPN",
                    ),
                    selected = routingMode,
                    onSelect = viewModel::setRoutingMode,
                )
                HintText(
                    when (routingMode) {
                        RoutingMode.SMART -> "Российские сайты и локальная сеть идут напрямую, реклама блокируется, остальное — через VPN."
                        RoutingMode.GLOBAL -> "Весь трафик идёт через VPN (кроме локальной сети). Без обхода РФ и блокировки рекламы."
                    },
                )
            }
        }
        item {
            SettingsCard("ДОМЕНЫ В ОБХОД (напрямую)") {
                DomainField(
                    value = directDomains,
                    onChange = viewModel::setDirectDomains,
                    placeholder = "example.com, mail.ru, *.gov.ru",
                )
                HintText("Через запятую или с новой строки. Эти домены пойдут мимо VPN.")
            }
        }
        item {
            SettingsCard("ДОМЕНЫ ЧЕРЕЗ VPN (принудительно)") {
                DomainField(
                    value = proxyDomains,
                    onChange = viewModel::setProxyDomains,
                    placeholder = "youtube.com, instagram.com",
                )
                HintText("Всегда идут через VPN, даже в «Умном» режиме и если попадают под обход РФ.")
            }
        }
    }
}

@Composable
private fun DomainField(value: String, onChange: (String) -> Unit, placeholder: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        placeholder = { Text(placeholder, style = MaterialTheme.typography.bodySmall) },
        textStyle = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.fillMaxWidth(),
        minLines = 2,
        maxLines = 5,
    )
}

@Composable
private fun AntiDpiTab(viewModel: SettingsViewModel) {
    val fragmentEnabled by viewModel.fragmentEnabled.collectAsState()
    val fragmentPackets by viewModel.fragmentPackets.collectAsState()
    val fragmentLength by viewModel.fragmentLength.collectAsState()
    val fragmentInterval by viewModel.fragmentInterval.collectAsState()
    val muxEnabled by viewModel.muxEnabled.collectAsState()
    val muxConcurrency by viewModel.muxConcurrency.collectAsState()

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            SettingsCard("ФРАГМЕНТАЦИЯ") {
                SwitchRow("Фрагментация TLS", fragmentEnabled, viewModel::setFragmentEnabled)
                HintText(
                    "Дробит TLS ClientHello на части, чтобы DPI не смог опознать и заблокировать " +
                        "соединение. Помогает при активных блокировках. Не применяется к «Автовыбору».",
                )
                if (fragmentEnabled) {
                    HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    LabeledField("Пакеты", fragmentPackets, viewModel::setFragmentPackets, "tlshello")
                    LabeledField("Длина", fragmentLength, viewModel::setFragmentLength, "100-200")
                    LabeledField("Интервал (мс)", fragmentInterval, viewModel::setFragmentInterval, "10-20")
                }
            }
        }
        item {
            SettingsCard("МУЛЬТИПЛЕКСИРОВАНИЕ (MUX)") {
                SwitchRow("Mux", muxEnabled, viewModel::setMuxEnabled)
                HintText(
                    "Объединяет несколько соединений в один канал — меньше рукопожатий, но может " +
                        "снизить скорость. Обычно лучше держать выключенным.",
                )
                if (muxEnabled) {
                    HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    StepperRow(
                        title = "Concurrency",
                        subtitle = "Число потоков в одном канале",
                        value = muxConcurrency,
                        step = 1,
                        range = 1..128,
                        onChange = viewModel::setMuxConcurrency,
                    )
                }
            }
        }
    }
}

/** A left-aligned label with an inline single-line text field on the right (fragment params). */
@Composable
private fun LabeledField(label: String, value: String, onChange: (String) -> Unit, placeholder: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.width(110.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            placeholder = { Text(placeholder, style = MaterialTheme.typography.bodySmall) },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun AboutTab(viewModel: SettingsViewModel, onOpenLogs: () -> Unit) {
    val context = LocalContext.current
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Lizercool (LC VPN)", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(
            "Версия ${BuildConfig.VERSION_NAME}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        )

        SettingsCard("ОТЛАДКА", modifier = Modifier.padding(top = 16.dp)) {
            NavRow(
                icon = Icons.Filled.Terminal,
                title = "Логи туннеля",
                subtitle = "Просмотр логов как в консоли",
                onClick = onOpenLogs,
            )
            HorizontalDivider(Modifier.padding(vertical = 4.dp))
            Button(
                onClick = {
                    val intent = viewModel.shareLogsIntent()
                    if (intent != null) context.startActivity(intent)
                },
                modifier = Modifier.padding(top = 8.dp),
            ) {
                Text("Поделиться логами")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LogViewerScreen(viewModel: SettingsViewModel, onBack: () -> Unit) {
    val context = LocalContext.current
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    var logs by remember { mutableStateOf("") }
    var reloadKey by remember { mutableIntStateOf(0) }

    LaunchedEffect(reloadKey) {
        logs = withContext(Dispatchers.IO) { viewModel.readLogs() }
    }

    val scrollState = rememberScrollState()
    // Jump to the newest lines whenever the content changes (console tail behaviour).
    LaunchedEffect(logs) { scrollState.scrollTo(scrollState.maxValue) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Логи туннеля") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Назад") }
                },
                actions = {
                    IconButton(onClick = { reloadKey++ }) { Icon(Icons.Filled.Refresh, contentDescription = "Обновить") }
                    IconButton(onClick = { clipboard.setText(AnnotatedString(logs)) }) {
                        Icon(Icons.Filled.ContentCopy, contentDescription = "Копировать")
                    }
                    IconButton(onClick = {
                        val intent = viewModel.shareLogsIntent()
                        if (intent != null) context.startActivity(intent)
                    }) { Icon(Icons.Filled.Share, contentDescription = "Экспорт") }
                    IconButton(onClick = { viewModel.clearLogs(); reloadKey++ }) {
                        Icon(Icons.Filled.Delete, contentDescription = "Очистить", tint = MaterialTheme.colorScheme.error)
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(Color(0xFF0B0F14)),
        ) {
            if (logs.isBlank()) {
                Text(
                    "Логи пусты. Подключитесь, чтобы началась запись.",
                    color = Color(0xFF8A94A6),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
            } else {
                Text(
                    logs,
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(scrollState)
                        .horizontalScroll(rememberScrollState())
                        .padding(12.dp),
                    color = Color(0xFFB9C2D0),
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    lineHeight = 15.sp,
                    softWrap = false,
                )
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

/** A label + monospace value with a copy-to-clipboard button (proxy address/login/password). */
@Composable
private fun CopyRow(label: String, value: String) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            modifier = Modifier.width(72.dp),
        )
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = { clipboard.setText(AnnotatedString(value)) }, modifier = Modifier.size(32.dp)) {
            Icon(
                Icons.Filled.ContentCopy,
                contentDescription = "Копировать $label",
                modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.primary,
            )
        }
    }
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
