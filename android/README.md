# MacRemote Android preview

This Kotlin app connects to a MacRemote relay over HTTPS. Its dark blue interface separates Home, Control, Activity, and Settings behind an animated bottom dock. It can request host status, screenshots, open-folder and lock actions, submit coding-agent tasks, and display recent command results. The host must approve coding-agent tasks locally before execution.

## Build

Requirements: Java 17, Android SDK platform 35, and Gradle 8.9.

```sh
gradle --no-daemon :app:assembleDebug
```

The installable preview APK is written to `app/build/outputs/apk/debug/app-debug.apk`. GitHub Actions also publishes this artifact for workflow runs that build the Android module. It is a debug APK, not a production-signed release.

## Pair

Run and expose the relay only behind HTTPS; see [`../relay/README.md`](../relay/README.md). Provision a host to receive a host ID, host token, and phone token. Enter the host token in the desktop host app and the phone token in this app. The app requires an HTTPS origin and stores the connection settings encrypted with a key in Android Keystore.

The relay is not end-to-end encrypted. Its operator can read queued prompts, screenshots, and command results.
