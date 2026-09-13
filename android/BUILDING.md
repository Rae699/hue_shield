# Build the Android relay

The included source is a small Java-only Android app. The script builds offline on macOS or Linux using tools you already installed. It never downloads an SDK and does not install anything on a device.

Requirements:

- Python 3.8 or newer, with no extra Python packages.
- A Java 11 or newer **JDK**, including `java`, `javac`, and `keytool`. Set `JAVA_HOME` if these tools are not on your path.
- Android SDK Platform 34 and Build Tools 34.0.0 for your operating system.

The SDK root must contain `platforms/android-34/android.jar` and `build-tools/34.0.0/`. Compilation uses platform 34 while the manifest deliberately preserves the original runtime's minimum Android 8/API 26 and target Android 11/API 30. A newer compile platform does not change that runtime target.

From the extracted package root, inspect the options and run the checks:

```sh
python3 android/build.py --help
python3 android/build.py --test-only
```

The tests need only Python and the JDK. They check the shared shortcut/callback contract, manifest, build configuration, controller timing and serialization, scene ordering, and Emby audio gating. A successful result is not a live-device test.

## Build with your own key

Set the installed SDK location, or pass it using `--sdk`:

```sh
export ANDROID_SDK_ROOT="/path/to/your/android-sdk"
```

Choose a **private local directory outside the extracted package** for your signing key. Keep this key for future updates to your own build. The script rejects keys inside the package, including paths that resolve there through a symlink.

The following shell example works with bash or zsh. It reads a password without displaying it and passes only the environment variable's name to the build script:

```sh
printf 'New local signing password (at least 6 characters): '
stty -echo
IFS= read -r HUE_RELAY_KEYSTORE_PASSWORD
stty echo
printf '\n'
export HUE_RELAY_KEYSTORE_PASSWORD

python3 android/build.py \
  --keystore "$HOME/.local/share/hue-sync-relay/local-signing.jks" \
  --password-env HUE_RELAY_KEYSTORE_PASSWORD \
  --generate-key

unset HUE_RELAY_KEYSTORE_PASSWORD
```

If the chosen key already exists, omit `--generate-key`. That option deliberately refuses to overwrite a key. The default key alias is `hue-sync-relay`; use `--alias` when signing with an existing key that has another alias. If the key and keystore passwords differ, use a second environment variable and `--key-password-env`.

The default result is `android/build/hue-sync-relay-1.0.0.apk`. `--output` chooses another output file. Each normal build runs the source checks, compiles, aligns, signs, verifies the signature and alignment, prints the package metadata, and reports a SHA-256 hash. Temporary compiled classes and unsigned files are removed automatically.

The APK contains a public signing certificate. It never contains the signing private key. Keep signing keys, passwords, user configuration, SDK files, and personalized shortcut imports out of anything you share.

## Updating and compatibility

The public application ID is `dev.huesync.relay`, separate from the original private relay. Android requires the same signing key for an in-place update of this public package. A build you sign locally generally cannot update over a separately obtained community APK: uninstall that APK first, or keep using APKs from one trusted signer. The relay has no launcher screen; installation and automation setup are covered by the package README.

This preserves the earlier controller algorithm and runtime target. The community package has offline source/build checks; actual behavior can depend on the Android TV device, Android version, HTTP Shortcuts version, and tvQuickActions setup. The build does not prove compatibility with every Android release.
