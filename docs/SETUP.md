# Set up Hue Sync Relay

Run the commands below from the extracted community package folder. They use your own devices and credentials. The generator works offline; pairing and the checks you perform after installation contact your devices. No AI model, API subscription or cloud relay is needed for normal operation.

This community APK and its generated configuration have offline/build validation. The public APK has not been installed on a TV, and the new imports have not been imported into the actual apps. The earlier original installation supplied the live-tested control logic; that does not constitute a live test of this newly configured package. See [TESTING.md](TESTING.md) for the validation boundary.

## 1. Prepare your own setup

You need an Android TV device such as SHIELD, a Hue Sync Box already configured in the Hue app, HTTP Shortcuts, tvQuickActions, and a computer with Python 3.8 or newer and Android platform-tools (`adb`). This import targets HTTP Shortcuts format 91, compatibility 90, and the tvQuickActions 3.7 export format. Use app versions that accept those formats.

Confirm video sync works manually in the Hue app. Identify the Sync Box HDMI input connected to your player, from 1 through 4. Keep the player and Sync Box reachable on your trusted local network; reserve their addresses if needed.

Export backups from HTTP Shortcuts and tvQuickActions before changing their settings. Review existing Hue automations and disable any that would also start/stop sync or control the same scenes. Keep unrelated rules. Do not reset either app or restore an unrelated backup over your setup.

## 2. Create private Sync Box configuration

Read [SECURITY.md](SECURITY.md) before entering credentials. Obtain and verify the SHA-256 fingerprint of **your Sync Box's leaf certificate** through your trusted setup or the official Philips API identity/CA procedure described there. A fingerprint is 64 hexadecimal characters with no colons.

Do not trust a fingerprint merely because it was returned by the first connection. Do not use a command that disables certificate verification as a substitute for verifying device identity.

If you already have a token for your own Sync Box:

```sh
cp config.example.json config.local.json
chmod 600 config.local.json
```

Edit these `ownSyncBox` fields in `config.local.json`:

| Field | Required value |
| --- | --- |
| `host` | Your hostname or IP address only; no `http://`, `https://`, port, path or query. A plain IPv6 address is accepted without brackets or a scope suffix. |
| `token` | Your existing Sync Box API token. |
| `certificateFingerprint` | Your verified 64-hex SHA-256 leaf-certificate fingerprint. |
| `input` | The integer `1`, `2`, `3` or `4` for your player's Sync Box HDMI input. |

Keep `optionalScenes.enabled` set to `false` for the initial setup. The unused scene placeholders can remain in the file while scenes are disabled. Example placeholders are rejected if used for an enabled feature.

Alternatively, register a new token with the pairing helper after verifying the fingerprint. Replace the uppercase placeholders and select your input:

```sh
python3 tools/pair_sync_box.py --host OWN_HOST --fingerprint VERIFIED64 --input 1 --output config.local.json
```

Follow the helper's prompt and hold the physical Sync Box button for about three seconds. It retries only the API's button-not-pressed response, code 16, for up to 45 seconds. Other errors stop pairing. It saves the token in the private configuration file; it does not print the token. Use a new output filename if a configuration already exists. Pairing is the only setup step here that registers a device credential.

Now generate the HTTP Shortcuts import:

```sh
python3 tools/generate_config.py config.local.json
```

The command prints the output path. With the filename above, the output is `generated/hue-relay-http-shortcuts.PRIVATE.zip`. The ZIP has owner-only permissions, and its directory has owner-only access. It contains your credentials: transfer it privately and never attach it, your configuration file, or your app backups to a public post.

## 3. Build and install the relay and HTTP Shortcuts entries

This source-only edition includes no APK. First follow [BUILDING.md](../android/BUILDING.md) and put your compiled APK at `releases/hue-sync-relay-1.0.0.apk`, or substitute your build output path below.

On SHIELD, enable Developer options by selecting the build number repeatedly in its About settings, then enable network debugging. Menu wording depends on the Android TV version. Use the address/port shown by your device and approve the computer's debugging connection on the TV. A typical connection is:

```sh
adb connect SHIELD_IP:5555
adb install releases/hue-sync-relay-1.0.0.apk
```

The relay package is `dev.huesync.relay`. It runs as a background service and has no launcher screen. For later updates signed with the same community key, use `adb install -r` with the new APK. Do not uninstall a different package to fix a signature mismatch without first reviewing what is installed.

Transfer the private HTTP Shortcuts ZIP to the TV. In HTTP Shortcuts, use its native file-import option. Review the import and add/update the **Hue Sync Relay** category; do not replace your entire existing configuration. The generated category contains **nine shortcut records**, whose fixed names and IDs are defined in [contract.json](../contract.json). They are intentionally hidden helpers. With scenes disabled, the scene helpers complete without making a network request.

Allow HTTP Shortcuts to run in the background, including any notification permission or troubleshooting setting it requests for reliable execution. Review the Android TV battery/background restrictions for both HTTP Shortcuts and the relay. A foreground-service notification is expected while automation is active.

## 4. Add tvQuickActions event rules with Merge

Make a **fresh native tvQuickActions export** after reviewing any competing Hue rules. Copy your own export to the computer and generate a scoped merge:

```sh
python3 tools/configure_tvqa.py --base OWN_EXPORT.zip --output generated/tvqa-community-merge.zip
```

The output preserves unrelated settings and existing lifecycle actions. It allocates IDs from your export and appends the relay action to each of the three lifecycle rules. The output may therefore contain private content from your backup; keep it private too.

If the tool refuses a lifecycle rule with constraints, or a disabled rule containing saved actions, review that rule in tvQuickActions. Decide which existing actions should run on each event, then make a fresh export. Do not delete unrelated actions to force the import through. The tool also refuses to overwrite an existing output ZIP; choose another output filename when regenerating.

Transfer the resulting ZIP to tvQuickActions and choose **Restore → Merge**. Never choose **Overwrite all**. Review the restored rules, grant the accessibility and notification-access permissions tvQuickActions needs for the selected event types, and confirm that the actual event macros are enabled. Importing a named intent alone does not enable an event rule.

The core mapping is:

| tvQuickActions event | Explicit broadcast action |
| --- | --- |
| Screen on | `dev.huesync.relay.SYNC_START` |
| Screen off | `dev.huesync.relay.SYNC_STOP` |
| Power on/boot | `dev.huesync.relay.SYNC_BOOT` |

If your tvQuickActions version cannot import this schema, create the three mappings manually. For each, use a **broadcast receiver** target with component `dev.huesync.relay/.SceneReceiver`, the action above, launch flags `0x20` (include stopped packages, as in the generated intents), and no extras. Attach the intent to the corresponding event macro and enable it. Do not configure these as activity launches or direct HTTP Shortcuts launches.

## 5. Verify on your devices

Keep scenes disabled for the first check. With the TV awake and valid video on the configured input, trigger Screen on or send this explicit broadcast:

```sh
adb shell am broadcast -f 0x20 -n dev.huesync.relay/.SceneReceiver -a dev.huesync.relay.SYNC_START
```

This starts real Sync Box checks and can enable video sync. Confirm the resulting state in the Hue app. The relay waits for the configured input to be linked and carry supported video; it does not start sync merely because the TV woke up.

Then use the normal sleep/wake and reboot controls. Confirm that sync turns off on sleep and resumes when video is ready after wake/boot. Off reconciliation includes a later confirmation, so allow the checks to finish. Recheck the three enabled event rules if manual broadcasts work but lifecycle events do not.

If a request fails, check the selected input, local connectivity, your token and the verified certificate fingerprint. Do not bypass the pin to make an error disappear. Once core behavior works, add optional room scenes using [SCENES.md](SCENES.md).

Keep the original public ZIP separate from your private configured files. Turn off network debugging when finished if you do not need it for ongoing maintenance.
