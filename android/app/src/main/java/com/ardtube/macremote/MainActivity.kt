package com.ardtube.macremote

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.content.Intent
import android.os.Bundle
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.DesktopWindows
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Security
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLDecoder
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : ComponentActivity() {
    private var pairingLink by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pairingLink = intent?.dataString
        enableEdgeToEdge(
            statusBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        val securePreferences = SecurePreferences(this)
        setContent {
            MaterialTheme(colorScheme = MacRemoteColorScheme) {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    RelayScreen(securePreferences, pairingLink)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        pairingLink = intent.dataString
    }
}

private val MacRemoteColorScheme = darkColorScheme(
    primary = Color(0xFF83B8FF),
    onPrimary = Color(0xFF09213D),
    primaryContainer = Color(0xFF173B63),
    onPrimaryContainer = Color(0xFFD8E9FF),
    secondary = Color(0xFF72D8E5),
    onSecondary = Color(0xFF06252B),
    background = Color(0xFF07111F),
    onBackground = Color(0xFFEAF2FC),
    surface = Color(0xFF0D1A2A),
    onSurface = Color(0xFFEAF2FC),
    surfaceVariant = Color(0xFF18283C),
    onSurfaceVariant = Color(0xFFA8B8CD),
    surfaceContainerLow = Color(0xFF0C1928),
    surfaceContainer = Color(0xFF112137),
    surfaceContainerHigh = Color(0xFF192B42),
    outline = Color(0xFF52657D),
    error = Color(0xFFFF9AA8),
    onError = Color(0xFF3A0710),
)

private enum class AppSection(val title: String, val label: String, val icon: ImageVector) {
    HOME("Your workspace", "Home", Icons.Outlined.Home),
    CONTROL("Remote control", "Control", Icons.Outlined.Tune),
    ACTIVITY("Activity", "Activity", Icons.Outlined.History),
    SETTINGS("Connection", "Settings", Icons.Outlined.Settings),
}

private data class RelaySettings(
    val relayUrl: String = "",
    val hostId: String = "",
    val phoneToken: String = "",
)

private data class RemoteCommand(
    val id: String,
    val action: String,
    val status: String,
    val createdAt: String,
    val details: String,
    val screenshot: Bitmap?,
    val hasScreenshot: Boolean,
)

private class SecurePreferences(context: android.content.Context) {
    private val preferences = context.getSharedPreferences("macremote-secure", android.content.Context.MODE_PRIVATE)
    private val keyAlias = "macremote-settings-v1"

    fun load(): RelaySettings {
        val saved = preferences.getString("settings", null) ?: return RelaySettings()
        val encrypted = Base64.decode(saved, Base64.NO_WRAP)
        require(encrypted.size > GCM_IV_LENGTH) { "Saved connection settings are corrupted." }
        val iv = encrypted.copyOfRange(0, GCM_IV_LENGTH)
        val ciphertext = encrypted.copyOfRange(GCM_IV_LENGTH, encrypted.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        val json = JSONObject(String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8))
        return RelaySettings(
            relayUrl = json.optString("relayUrl"),
            hostId = json.optString("hostId"),
            phoneToken = json.optString("phoneToken"),
        )
    }

    fun save(settings: RelaySettings) {
        val json = JSONObject()
            .put("relayUrl", settings.relayUrl)
            .put("hostId", settings.hostId)
            .put("phoneToken", settings.phoneToken)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.iv + cipher.doFinal(json)
        check(preferences.edit().putString("settings", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit()) {
            "Could not save encrypted connection settings."
        }
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val GCM_IV_LENGTH = 12
        const val GCM_TAG_BITS = 128
    }
}

@Composable
private fun RelayScreen(securePreferences: SecurePreferences, pairingLink: String?) {
    var settings by remember { mutableStateOf(RelaySettings()) }
    var relayUrl by remember { mutableStateOf("") }
    var hostId by remember { mutableStateOf("") }
    var phoneToken by remember { mutableStateOf("") }
    var settingsLoaded by remember { mutableStateOf(false) }
    var connectionStatus by remember { mutableStateOf("Set up a secure relay connection") }
    var lastSeen by remember { mutableStateOf("") }
    var commands by remember { mutableStateOf<List<RemoteCommand>>(emptyList()) }
    var prompt by remember { mutableStateOf("") }
    var folderPath by remember { mutableStateOf("") }
    var provider by remember { mutableStateOf("Claude Code") }
    var providerMenuOpen by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var selectedSection by remember { mutableStateOf(AppSection.HOME) }
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val hasConnection = settings.relayUrl.isNotBlank() &&
        settings.hostId.isNotBlank() &&
        settings.phoneToken.isNotBlank()

    LaunchedEffect(Unit) {
        try {
            settings = withContext(Dispatchers.IO) { securePreferences.load() }
            relayUrl = settings.relayUrl
            hostId = settings.hostId
            phoneToken = settings.phoneToken
        } catch (error: Exception) {
            errorMessage = error.message ?: "Could not decrypt saved connection settings."
        } finally {
            settingsLoaded = true
        }
    }

    LaunchedEffect(settingsLoaded, pairingLink) {
        if (!settingsLoaded || pairingLink.isNullOrBlank()) return@LaunchedEffect
        try {
            val imported = parsePairingLink(pairingLink)
            relayUrl = imported.relayUrl
            hostId = imported.hostId
            phoneToken = imported.phoneToken
            selectedSection = AppSection.SETTINGS
            connectionStatus = "Pairing imported · save to connect"
            errorMessage = null
        } catch (error: IllegalArgumentException) {
            errorMessage = error.message ?: "The pairing link is invalid."
        } catch (error: java.net.URISyntaxException) {
            errorMessage = "The pairing link is invalid."
        }
    }

    LaunchedEffect(settings, lifecycle) {
        if (settings.relayUrl.isBlank() || settings.hostId.isBlank() || settings.phoneToken.isBlank()) return@LaunchedEffect
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                try {
                    val host = withContext(Dispatchers.IO) { RelayApi.getHost(settings) }
                    commands = host.commands
                    lastSeen = host.lastSeenAt
                    connectionStatus = "Connected to ${host.name}"
                    errorMessage = null
                } catch (error: IOException) {
                    connectionStatus = "Relay connection failed"
                    errorMessage = error.message ?: "Could not reach the relay."
                } catch (error: IllegalArgumentException) {
                    connectionStatus = "Connection settings need attention"
                    errorMessage = error.message ?: "Check the relay URL and pairing details."
                } catch (error: JSONException) {
                    connectionStatus = "Relay returned an invalid response"
                    errorMessage = error.message ?: "The relay response could not be read."
                }
                delay(5_000)
            }
        }
    }

    fun saveConnection() {
        scope.launch {
            busy = true
            errorMessage = null
            try {
                val updated = RelaySettings(relayUrl.trim().trimEnd('/'), hostId.trim(), phoneToken.trim())
                RelayApi.validate(updated)
                withContext(Dispatchers.IO) { securePreferences.save(updated) }
                settings = updated
                connectionStatus = "Connecting securely…"
            } catch (error: Exception) {
                errorMessage = error.message ?: "Could not save connection settings."
            } finally {
                busy = false
            }
        }
    }

    fun sendAction(action: String, payload: JSONObject = JSONObject()) {
        scope.launch {
            busy = true
            errorMessage = null
            try {
                RelayApi.queueCommand(settings, action, payload)
                connectionStatus = "Command sent · waiting for host"
                commands = withContext(Dispatchers.IO) { RelayApi.getHost(settings).commands }
            } catch (error: IOException) {
                errorMessage = error.message ?: "Could not send command."
            } catch (error: IllegalArgumentException) {
                errorMessage = error.message ?: "Check the relay connection settings."
            } finally {
                busy = false
            }
        }
    }

    fun loadScreenshot(command: RemoteCommand) {
        scope.launch {
            busy = true
            errorMessage = null
            try {
                val updated = withContext(Dispatchers.IO) {
                    RelayApi.getCommand(settings, command.id)
                }
                commands = commands.map { if (it.id == command.id) updated else it }
            } catch (error: IOException) {
                errorMessage = error.message ?: "Could not load the screenshot."
            } finally {
                busy = false
            }
        }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            BottomDock(selected = selectedSection, onSelect = { selectedSection = it })
        },
    ) { contentPadding ->
        AnimatedContent(
            targetState = selectedSection,
            modifier = Modifier.fillMaxSize().padding(contentPadding),
            transitionSpec = {
                (fadeIn(tween(180)) + slideInHorizontally(tween(180)) { it / 18 }) togetherWith
                    (fadeOut(tween(120)) + slideOutHorizontally(tween(120)) { -it / 18 })
            },
            label = "MacRemote section transition",
        ) { section ->
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 20.dp, top = 18.dp, end = 20.dp, bottom = 28.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                item { AppHeader(section) }
                item { HostStatusCard(connectionStatus, lastSeen) }
                if (errorMessage != null) {
                    item { ErrorBanner(errorMessage.orEmpty()) }
                }
                when (section) {
                    AppSection.HOME -> {
                        item {
                            HomeSection(
                                hasConnection = hasConnection,
                                commands = commands.take(3),
                                onOpenSettings = { selectedSection = AppSection.SETTINGS },
                                onOpenActivity = { selectedSection = AppSection.ACTIVITY },
                                onAction = { action -> sendAction(action) },
                                onScreenshot = ::loadScreenshot,
                                busy = busy,
                            )
                        }
                    }

                    AppSection.CONTROL -> {
                        item {
                            ControlSection(
                                folderPath = folderPath,
                                onFolderPathChange = { folderPath = it },
                                prompt = prompt,
                                onPromptChange = { prompt = it },
                                provider = provider,
                                providerMenuOpen = providerMenuOpen,
                                onProviderMenuOpenChange = { providerMenuOpen = it },
                                onProviderChange = { provider = it },
                                hasConnection = hasConnection,
                                busy = busy,
                                onAction = ::sendAction,
                            )
                        }
                    }

                    AppSection.ACTIVITY -> {
                        if (commands.isEmpty()) {
                            item { EmptyActivity() }
                        } else {
                            items(commands, key = { it.id }) { command ->
                                ActivityCard(
                                    command = command,
                                    busy = busy,
                                    onLoadScreenshot = { loadScreenshot(command) },
                                )
                            }
                        }
                    }

                    AppSection.SETTINGS -> {
                        item {
                            ConnectionSettings(
                                relayUrl = relayUrl,
                                onRelayUrlChange = { relayUrl = it },
                                hostId = hostId,
                                onHostIdChange = { hostId = it },
                                phoneToken = phoneToken,
                                onPhoneTokenChange = { phoneToken = it },
                                settingsLoaded = settingsLoaded,
                                busy = busy,
                                onSave = ::saveConnection,
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun parsePairingLink(raw: String): RelaySettings {
    val uri = URI(raw)
    require(uri.scheme == "macremote" && uri.host == "pair" && uri.rawUserInfo == null) {
        "This is not a MacRemote pairing link."
    }
    val values = uri.rawQuery.orEmpty()
        .split('&')
        .filter(String::isNotBlank)
        .associate { item ->
            val parts = item.split('=', limit = 2)
            URLDecoder.decode(parts[0], StandardCharsets.UTF_8.name()) to
                URLDecoder.decode(parts.getOrElse(1) { "" }, StandardCharsets.UTF_8.name())
        }
    val settings = RelaySettings(
        relayUrl = values["relay_url"].orEmpty(),
        hostId = values["host_id"].orEmpty(),
        phoneToken = values["phone_token"].orEmpty(),
    )
    RelayApi.validate(settings)
    return settings
}

@Composable
private fun BottomDock(selected: AppSection, onSelect: (AppSection) -> Unit) {
    NavigationBar(
        modifier = Modifier
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(26.dp)),
        containerColor = MaterialTheme.colorScheme.surfaceContainer,
        tonalElevation = 0.dp,
    ) {
        AppSection.entries.forEach { section ->
            NavigationBarItem(
                selected = selected == section,
                onClick = { onSelect(section) },
                icon = { Icon(section.icon, contentDescription = null) },
                label = { Text(section.label) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = MaterialTheme.colorScheme.primary,
                    selectedTextColor = MaterialTheme.colorScheme.primary,
                    indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                    unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                ),
            )
        }
    }
}

@Composable
private fun AppHeader(section: AppSection) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Surface(shape = RoundedCornerShape(15.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                Icon(
                    Icons.Outlined.DesktopWindows,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(11.dp).size(24.dp),
                )
            }
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("MACREMOTE", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary, fontWeight = FontWeight.Bold)
                Text("A little closer to home.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(section.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                text = when (section) {
                    AppSection.HOME -> "Your computer, ready when you are."
                    AppSection.CONTROL -> "Useful tools, right at your fingertips."
                    AppSection.ACTIVITY -> "A clear record of requests and results."
                    AppSection.SETTINGS -> "Securely pair your phone and computer."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun HostStatusCard(connectionStatus: String, lastSeen: String) {
    val connected = connectionStatus.startsWith("Connected")
    val indicatorColor by animateColorAsState(
        targetValue = if (connected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.outline,
        animationSpec = tween(350),
        label = "connection status color",
    )
    PanelCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Surface(shape = CircleShape, color = if (connected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh) {
                Icon(
                    Icons.Outlined.DesktopWindows,
                    contentDescription = null,
                    tint = if (connected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(12.dp).size(22.dp),
                )
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text("YOUR COMPUTER", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Bold)
                Text(connectionStatus, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                if (lastSeen.isNotBlank()) {
                    Text("Last seen $lastSeen", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(modifier = Modifier.size(9.dp).background(indicatorColor, CircleShape))
        }
    }
}

@Composable
private fun HomeSection(
    hasConnection: Boolean,
    commands: List<RemoteCommand>,
    onOpenSettings: () -> Unit,
    onOpenActivity: () -> Unit,
    onAction: (String) -> Unit,
    onScreenshot: (RemoteCommand) -> Unit,
    busy: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!hasConnection) {
            PanelCard {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                    Icon(Icons.Outlined.Security, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("One quick setup", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text("Add your private HTTPS relay details to connect your computer.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        TextButton(onClick = onOpenSettings) {
                            Text("Set up connection")
                            Icon(Icons.AutoMirrored.Outlined.ArrowForward, contentDescription = null, modifier = Modifier.padding(start = 6.dp).size(17.dp))
                        }
                    }
                }
            }
        }

        SectionHeading("Quick actions", "Send a simple request to your computer")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            QuickActionCard(
                label = "Status",
                icon = Icons.Outlined.Refresh,
                enabled = hasConnection && !busy,
                modifier = Modifier.weight(1f),
            ) { onAction("status") }
            QuickActionCard(
                label = "Screenshot",
                icon = Icons.Outlined.PhotoCamera,
                enabled = hasConnection && !busy,
                modifier = Modifier.weight(1f),
            ) { onAction("screenshot") }
            QuickActionCard(
                label = "Lock",
                icon = Icons.Outlined.Lock,
                enabled = hasConnection && !busy,
                modifier = Modifier.weight(1f),
            ) { onAction("lock") }
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                SectionHeading("Recent activity", "Your latest remote requests")
            }
            TextButton(onClick = onOpenActivity) { Text("See all") }
        }
        if (commands.isEmpty()) {
            EmptyActivity(compact = true)
        } else {
            commands.forEach { command ->
                ActivityCard(command = command, busy = busy, onLoadScreenshot = { onScreenshot(command) })
            }
        }
    }
}

@Composable
private fun ControlSection(
    folderPath: String,
    onFolderPathChange: (String) -> Unit,
    prompt: String,
    onPromptChange: (String) -> Unit,
    provider: String,
    providerMenuOpen: Boolean,
    onProviderMenuOpenChange: (Boolean) -> Unit,
    onProviderChange: (String) -> Unit,
    hasConnection: Boolean,
    busy: Boolean,
    onAction: (String, JSONObject) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!hasConnection) {
            InfoBanner("Connect your computer in Settings before sending remote requests.")
        }
        SectionHeading("Shortcuts", "Fast, safe actions for this host")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            QuickActionCard("Status", Icons.Outlined.Refresh, hasConnection && !busy, Modifier.weight(1f)) {
                onAction("status", JSONObject())
            }
            QuickActionCard("Screenshot", Icons.Outlined.PhotoCamera, hasConnection && !busy, Modifier.weight(1f)) {
                onAction("screenshot", JSONObject())
            }
            QuickActionCard("Lock", Icons.Outlined.Lock, hasConnection && !busy, Modifier.weight(1f)) {
                onAction("lock", JSONObject())
            }
        }

        PanelCard {
            SectionHeading("Open a folder", "Jump to a known folder on your host")
            OutlinedTextField(
                value = folderPath,
                onValueChange = onFolderPathChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Folder path") },
                placeholder = { Text("/Users/you/Projects") },
                singleLine = true,
            )
            Button(
                onClick = { onAction("open_folder", JSONObject().put("path", folderPath)) },
                enabled = hasConnection && !busy && folderPath.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Outlined.FolderOpen, contentDescription = null)
                Text("Open folder", modifier = Modifier.padding(start = 8.dp))
            }
        }

        PanelCard {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Outlined.SmartToy, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                SectionHeading("Ask a coding agent", "The host must approve before work begins")
            }
            OutlinedButton(onClick = { onProviderMenuOpenChange(true) }) {
                Text(provider)
            }
            DropdownMenu(expanded = providerMenuOpen, onDismissRequest = { onProviderMenuOpenChange(false) }) {
                listOf("Claude Code", "Antigravity").forEach { option ->
                    DropdownMenuItem(
                        text = { Text(option) },
                        onClick = {
                            onProviderChange(option)
                            onProviderMenuOpenChange(false)
                        },
                    )
                }
            }
            OutlinedTextField(
                value = prompt,
                onValueChange = onPromptChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("What should it do?") },
                placeholder = { Text("Describe one task clearly…") },
                supportingText = { Text("${prompt.length}/4000 characters") },
                minLines = 3,
                maxLines = 6,
            )
            Button(
                onClick = {
                    val providerId = if (provider == "Claude Code") "claude" else "antigravity"
                    onAction("agent_task", JSONObject().put("provider", providerId).put("prompt", prompt))
                },
                enabled = hasConnection && !busy && prompt.isNotBlank() && prompt.length <= 4000,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Outlined.Security, contentDescription = null)
                Text("Send for host approval", modifier = Modifier.padding(start = 8.dp))
            }
        }
    }
}

@Composable
private fun ConnectionSettings(
    relayUrl: String,
    onRelayUrlChange: (String) -> Unit,
    hostId: String,
    onHostIdChange: (String) -> Unit,
    phoneToken: String,
    onPhoneTokenChange: (String) -> Unit,
    settingsLoaded: Boolean,
    busy: Boolean,
    onSave: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        PanelCard {
            SectionHeading("Pair your computer", "Use the private details created by your relay")
            OutlinedTextField(
                value = relayUrl,
                onValueChange = onRelayUrlChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("HTTPS relay URL") },
                placeholder = { Text("https://relay.example.com") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            )
            OutlinedTextField(
                value = hostId,
                onValueChange = onHostIdChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Host ID") },
                singleLine = true,
            )
            OutlinedTextField(
                value = phoneToken,
                onValueChange = onPhoneTokenChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Phone token") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
            )
            Button(
                onClick = onSave,
                enabled = settingsLoaded && !busy,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (busy) "Saving securely…" else "Save connection")
            }
        }
        InfoBanner("Connection details are encrypted on this phone with Android Keystore. Use a relay you trust.")
    }
}

@Composable
private fun ActivityCard(command: RemoteCommand, busy: Boolean, onLoadScreenshot: () -> Unit) {
    PanelCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                command.action.replace('_', ' ').replaceFirstChar { it.uppercase() },
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Surface(shape = RoundedCornerShape(40.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                Text(
                    command.status.replace('_', ' '),
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
        }
        Text(command.createdAt, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (command.details.isNotBlank()) Text(command.details, style = MaterialTheme.typography.bodyMedium)
        if (command.hasScreenshot && command.screenshot == null) {
            OutlinedButton(onClick = onLoadScreenshot, enabled = !busy) {
                Icon(Icons.Outlined.PhotoCamera, contentDescription = null)
                Text("Load screenshot", modifier = Modifier.padding(start = 8.dp))
            }
        }
        command.screenshot?.let { bitmap ->
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = "Remote screenshot",
                modifier = Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(16.dp)),
                contentScale = ContentScale.Fit,
            )
        }
    }
}

@Composable
private fun EmptyActivity(compact: Boolean = false) {
    PanelCard {
        Icon(
            Icons.Outlined.History,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(24.dp),
        )
        Text(
            if (compact) "Your recent requests will show up here." else "No activity yet",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        if (!compact) {
            Text("When you send an action to your computer, its status and result will appear here.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun QuickActionCard(
    label: String,
    icon: ImageVector,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.animateContentSize(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainer,
            disabledContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp, horizontal = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun PanelCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().animateContentSize(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content,
        )
    }
}

@Composable
private fun SectionHeading(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        if (subtitle.isNotBlank()) {
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun InfoBanner(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.primaryContainer,
    ) {
        Row(
            modifier = Modifier.padding(15.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.Security, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Text(message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
        }
    }
}

@Composable
private fun ErrorBanner(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.error.copy(alpha = 0.12f),
    ) {
        Text(
            message,
            modifier = Modifier.padding(15.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.error,
        )
    }
}

private data class HostSnapshot(
    val name: String,
    val lastSeenAt: String,
    val commands: List<RemoteCommand>,
)

private object RelayApi {
    fun validate(settings: RelaySettings) {
        val uri = try {
            URI(settings.relayUrl)
        } catch (_: java.net.URISyntaxException) {
            throw IllegalArgumentException("Enter a valid HTTPS relay URL.")
        }
        require(uri.scheme?.equals("https", ignoreCase = true) == true && !uri.host.isNullOrBlank()) {
            "The relay URL must use HTTPS."
        }
        require(uri.port == -1 || uri.port in 1..65535) { "The relay port is invalid." }
        require(uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty() in listOf("", "/")) {
            "Enter only the relay origin, without a path, query, or credentials."
        }
        require(settings.hostId.matches(Regex("[A-Za-z0-9_-]{16,64}"))) { "The host ID is invalid." }
        require(settings.phoneToken.length >= 40) { "The phone token is invalid." }
    }

    fun getHost(settings: RelaySettings): HostSnapshot {
        validate(settings)
        val response = request("${settings.relayUrl}/v1/hosts/${settings.hostId}", settings.phoneToken)
        val commands = response.optJSONArray("commands") ?: JSONArray()
        return HostSnapshot(
            name = response.optString("name", "Host"),
            lastSeenAt = response.optString("lastSeenAt").takeIf { it != "null" }.orEmpty(),
            commands = (0 until commands.length()).mapNotNull { index ->
                commands.optJSONObject(index)?.let(::parseCommand)
            },
        )
    }

    fun queueCommand(settings: RelaySettings, action: String, payload: JSONObject) {
        validate(settings)
        val body = JSONObject(payload.toString()).put("action", action)
        request("${settings.relayUrl}/v1/hosts/${settings.hostId}/commands", settings.phoneToken, body)
    }

    fun getCommand(settings: RelaySettings, commandId: String): RemoteCommand {
        validate(settings)
        val response = request(
            "${settings.relayUrl}/v1/hosts/${settings.hostId}/commands/$commandId",
            settings.phoneToken,
        )
        return parseCommand(response)
    }

    private fun parseCommand(json: JSONObject): RemoteCommand {
        val result = json.optJSONObject("result")
        val text = result?.optString("text").orEmpty().takeUnless { it == "null" }.orEmpty()
        val error = result?.optString("error").orEmpty().takeUnless { it == "null" }.orEmpty()
        val screenshotData = result?.optString("imageBase64").orEmpty().takeUnless { it == "null" }.orEmpty()
        val bitmap = if (screenshotData.isNotBlank()) decodeScreenshot(screenshotData) else null
        val screenshotError = if (screenshotData.isNotBlank() && bitmap == null) "Screenshot preview unavailable." else ""
        return RemoteCommand(
            id = json.optString("id"),
            action = json.optString("action"),
            status = json.optString("status"),
            createdAt = json.optString("createdAt"),
            details = listOf(text, error, screenshotError).filter { it.isNotBlank() }.joinToString("\n"),
            screenshot = bitmap,
            hasScreenshot = screenshotData.isNotBlank() || result?.optBoolean("hasScreenshot") == true,
        )
    }

    private fun decodeScreenshot(data: String): Bitmap? {
        if (data.length > MAX_SCREENSHOT_BASE64_CHARS) return null
        return try {
            val bytes = Base64.decode(data, Base64.DEFAULT)
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
            var sampleSize = 1
            while (bounds.outWidth / sampleSize > MAX_SCREENSHOT_DIMENSION ||
                bounds.outHeight / sampleSize > MAX_SCREENSHOT_DIMENSION
            ) {
                sampleSize *= 2
            }
            BitmapFactory.decodeByteArray(
                bytes,
                0,
                bytes.size,
                BitmapFactory.Options().apply { inSampleSize = sampleSize },
            )
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private const val MAX_SCREENSHOT_BASE64_CHARS = 5_600_000
    private const val MAX_SCREENSHOT_DIMENSION = 2048

    private fun request(url: String, token: String, body: JSONObject? = null): JSONObject {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = if (body == null) "GET" else "POST"
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) {
                connection.outputStream.bufferedWriter(StandardCharsets.UTF_8).use { it.write(body.toString()) }
            }
            val statusCode = connection.responseCode
            val stream = if (statusCode in 200..299) connection.inputStream else connection.errorStream
            val responseText = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (statusCode !in 200..299) {
                val message = try {
                    JSONObject(responseText).optString("error").takeIf { it.isNotBlank() }
                } catch (_: JSONException) {
                    null
                }
                throw IOException(message ?: "Relay request failed with HTTP $statusCode.")
            }
            return JSONObject(responseText)
        } finally {
            connection.disconnect()
        }

    }
}
