# MacRemote relay

The relay is a small Node.js 22.13+ service. It accepts short-lived host polls and phone commands over HTTPS and stores them in SQLite. Host agents make outbound requests; no inbound port on the controlled computer is required.

## Development

Run the tests and start the relay locally:

```sh
npm --prefix relay test
MRA_RELAY_ADMIN_KEY="$(openssl rand -base64 32)" node relay/server.js
```

By default the HTTP server binds to `127.0.0.1:8787`. It is not safe to expose this HTTP listener directly to the internet. Put a TLS reverse proxy in front; `Caddyfile.example` shows the proxy target. For a container, set `MRA_RELAY_BIND=0.0.0.0` only when the container ingress enforces HTTPS.

Set `MRA_RELAY_ADMIN_KEY` to a random secret of at least 32 bytes and `MRA_RELAY_DATA_DIR` to persistent storage. Do not commit the admin key or the relay database.

## Provisioning a host

Provisioning issues a host token and a phone token exactly once. Keep the output private; the phone token grants remote control of that host.

```sh
MRA_RELAY_URL=https://relay.example.com \
MRA_RELAY_ADMIN_KEY="$MRA_RELAY_ADMIN_KEY" \
node relay/provision-host.js "Office Mac"
```

The host app stores the host token; the phone app stores the phone token. The relay stores SHA-256 hashes of both tokens. Losing either token requires provisioning a replacement.

The relay validates a small action allowlist and rejects arbitrary shell actions. Coding-agent prompts remain subject to local approval by the host app. **Transport is protected by HTTPS, but this initial relay is not end-to-end encrypted:** its server can read queued prompts, status results, and screenshots. Host it only on infrastructure you trust. No public relay is deployed by this repository.

## Connecting the apps

1. In the macOS or Windows host app, enter the HTTPS relay URL, host ID, and host token.
2. Build/install the Android debug APK from the `macremote-android-debug` artifact in the desktop build workflow, or build it locally with Java 17, Android SDK 35, and Gradle 8.9:

   ```sh
   cd android
   gradle --no-daemon :app:assembleDebug
   ```

3. In Android, enter the same HTTPS relay URL and host ID, plus the phone token. The app encrypts these settings with Android Keystore.

The Android APK produced by CI is a debug build intended for preview/testing, not a production-signed release. Android rejects non-HTTPS relay URLs. Public releases require a separate release-signing setup.
