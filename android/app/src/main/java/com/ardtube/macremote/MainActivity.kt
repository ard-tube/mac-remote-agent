package com.ardtube.macremote

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
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
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val securePreferences = SecurePreferences(this)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    RelayScreen(securePreferences)
                }
            }
        }
    }
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
private fun RelayScreen(securePreferences: SecurePreferences) {
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
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle

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

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(modifier = Modifier.padding(top = 28.dp)) {
                Text("MacRemote", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text("Secure remote control for your Mac or Windows PC.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Spacer(
                        modifier = Modifier.size(10.dp)
                            .background(if (connectionStatus.startsWith("Connected")) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline, CircleShape),
                    )
                    Column {
                        Text(connectionStatus, fontWeight = FontWeight.SemiBold)
                        if (lastSeen.isNotBlank()) Text("Host last seen $lastSeen", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item {
            Card {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("Connect your host", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    Text("Use the relay URL, host ID, and phone token from your private provisioning output.", style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(
                        value = relayUrl,
                        onValueChange = { relayUrl = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("HTTPS relay URL") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    )
                    OutlinedTextField(
                        value = hostId,
                        onValueChange = { hostId = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Host ID") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = phoneToken,
                        onValueChange = { phoneToken = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Phone token") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                    )
                    Button(onClick = ::saveConnection, enabled = settingsLoaded && !busy, modifier = Modifier.fillMaxWidth()) {
                        Text("Save encrypted connection")
                    }
                }
            }
        }
        item {
            Card {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("Quick actions", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { sendAction("status") }, enabled = !busy) { Text("Status") }
                        OutlinedButton(onClick = { sendAction("screenshot") }, enabled = !busy) { Text("Screenshot") }
                        OutlinedButton(onClick = { sendAction("lock") }, enabled = !busy) { Text("Lock") }
                    }
                    OutlinedTextField(
                        value = folderPath,
                        onValueChange = { folderPath = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Folder path to open") },
                        singleLine = true,
                    )
                    OutlinedButton(
                        onClick = { sendAction("open_folder", JSONObject().put("path", folderPath)) },
                        enabled = !busy && folderPath.isNotBlank(),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Open folder") }
                }
            }
        }
        item {
            Card {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("Coding-agent task", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    Text("Every task waits for approval on the host computer before it runs.", style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = { providerMenuOpen = true }) { Text("Provider: $provider") }
                    DropdownMenu(expanded = providerMenuOpen, onDismissRequest = { providerMenuOpen = false }) {
                        listOf("Claude Code", "Antigravity").forEach { option ->
                            DropdownMenuItem(
                                text = { Text(option) },
                                onClick = {
                                    provider = option
                                    providerMenuOpen = false
                                },
                            )
                        }
                    }
                    OutlinedTextField(
                        value = prompt,
                        onValueChange = { prompt = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Describe the task") },
                        minLines = 3,
                    )
                    Button(
                        onClick = {
                            val providerId = if (provider == "Claude Code") "claude" else "antigravity"
                            sendAction("agent_task", JSONObject().put("provider", providerId).put("prompt", prompt))
                        },
                        enabled = !busy && prompt.isNotBlank() && prompt.length <= 4000,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Send for host approval") }
                }
            }
        }
        if (errorMessage != null) {
            item {
                Text(
                    text = errorMessage.orEmpty(),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
            }
        }
        item {
            Text("Recent activity", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        }
        if (commands.isEmpty()) {
            item { Text("Commands and host responses will appear here.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        } else {
            items(commands, key = { it.id }) { command ->
                Card(shape = RoundedCornerShape(16.dp)) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(command.action.replace('_', ' ').replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.SemiBold)
                            Text(command.status.replace('_', ' '), color = MaterialTheme.colorScheme.primary)
                        }
                        Text(command.createdAt, style = MaterialTheme.typography.labelSmall)
                        if (command.details.isNotBlank()) Text(command.details, style = MaterialTheme.typography.bodyMedium)
                        if (command.hasScreenshot && command.screenshot == null) {
                            OutlinedButton(
                                onClick = {
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
                                },
                                enabled = !busy,
                            ) { Text("Load screenshot") }
                        }
                        command.screenshot?.let { bitmap ->
                            Image(
                                bitmap = bitmap.asImageBitmap(),
                                contentDescription = "Remote screenshot",
                                modifier = Modifier.fillMaxWidth().height(220.dp),
                                contentScale = ContentScale.Fit,
                            )
                        }
                    }
                }
            }
        }
        item { Spacer(modifier = Modifier.height(12.dp)) }
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
