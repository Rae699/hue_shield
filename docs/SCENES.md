# Optional room scenes

Scenes are disabled by default. Core Sync Box start/stop does not require a Bridge key, room scene IDs or a sensor. Finish [SETUP.md](SETUP.md) before enabling scenes.

The optional mode recalls **your existing Hue Bridge v2 scenes**. Create the Cinema, Pause and Read scenes in your own Hue setup first and choose the lights each should affect. This package does not create rooms, entertainment areas, scenes or sensor resources.

## Configure your Bridge and resources

Edit `optionalScenes` in your private `config.local.json`. If the pairing helper created the file, its scene section contains only `enabled: false`: copy the full `optionalScenes` object from [config.example.json](../config.example.json), fill its fields below, and keep your existing `ownSyncBox` object unchanged.

| Field | Value |
| --- | --- |
| `enabled` | `true` to enable the feature. |
| `ownBridge.host` | Your Bridge hostname or IP address only. The same host rules as `ownSyncBox.host` apply. |
| `ownBridge.applicationKey` | Your own authorized Hue Bridge application key. This is separate from the Sync Box token. |
| `ownBridge.certificateFingerprint` | The verified 64-hex SHA-256 fingerprint of your Bridge leaf certificate. Follow [SECURITY.md](SECURITY.md). |
| `scenes.cinema` | UUID of your Cinema **scene resource**. |
| `scenes.pause` | UUID of your Pause scene resource. |
| `scenes.read` | UUID of your Read scene resource. |
| `readGuard.sensorResourceId` | UUID of your sensor's **light_level resource**, not its device or motion resource. |
| `readGuard.start` | Start of the allowed scene window, using local TV time in `HH:MM` form. Default `20:00`, inclusive. |
| `readGuard.end` | End of that window. Default `06:00`, exclusive. It must differ from the start. |
| `readGuard.luxThreshold` | Maximum permitted **raw Hue `light_level` reading**, from 0 through 65535. Default `2000`. Despite the field name, this is not a measurement in physical lux. |
| `readGuard.readFailOpen` | Optional boolean; defaults to `true`. Controls what happens if the sensor request fails or its reading is unavailable/invalid. |

Use your own trusted Bridge API setup to obtain its application key and inspect the v2 `scene` and `light_level` resource lists. The corresponding endpoints are `/clip/v2/resource/scene` and `/clip/v2/resource/light_level`; requests authenticate with the `hue-application-key` header. Do not substitute a scene name, old numeric scene ID, room UUID or sensor device UUID for the required resource UUID. Verify the Bridge certificate before sending its key.

The time window applies to Cinema, Pause and Read. Windows may cross midnight, such as `20:00`–`06:00`, or stay within one day, such as `07:00`–`19:00`. Check the TV's clock and time zone. Start and end cannot be identical.

Regenerate your private import and import it into HTTP Shortcuts:

```sh
python3 tools/generate_config.py config.local.json
```

The import still contains exactly **nine shortcut records**. Enabling scenes adds two persistent, namespaced state variables for the current scene and last Cinema time. The Cycle target and next index exist only for the current request. No original installation's variables or resource IDs are reused.

## Scene behavior

| Relay action | Behavior |
| --- | --- |
| `CINEMA` | During the configured time window, recall Cinema. The relay also checks whether video sync should start. |
| `PAUSE` | The relay delays Pause by three seconds, so resumed playback can cancel it. During the configured time window, recall Pause. |
| `READ` | Check the time window, the recent-Cinema guard and sensor reading. Recall Read only if the resulting decision permits it. |
| `CYCLE` | Manually cycle Cinema → Pause → Read → Cinema. This intentionally bypasses the time and sensor guards. |

The recent-Cinema guard blocks Read for three seconds after a successful Cinema recall. A valid sensor reading permits Read when `light_level <= luxThreshold` and blocks it above the threshold. If `readFailOpen` is `true`, unavailable or invalid sensor data permits Read **only when the time and recent-Cinema guards permit it**. Set it to `false` to skip Read when the sensor cannot be checked. The setting does not bypass certificate verification; it determines the scene decision after a failed sensor request.

The relay serializes Read into a `READ_CHECK` request and a separate `READ_RECALL` request. A newer scene choice or sleep event cancels an obsolete Read decision. The reserved HTTP Shortcuts entry named **Hue Relay - Read** is a harmless no-op if launched by itself: use the relay's `READ` broadcast for the complete behavior. Do not bind media buttons or event rules directly to `READ_CHECK` or `READ_RECALL`.

Each dispatched HTTP helper performs one top-level request; the complete Read flow uses two successive helpers. The scripts do not launch nested shortcuts, queue additional activities or perform their own background polling. Skipped Cinema/Pause and disabled scene entries complete without contacting the Bridge. Read Check may still contact the sensor outside the allowed window, but it returns a decision that prevents scene recall.

## Connect scenes to tvQuickActions

Export a fresh tvQuickActions backup and regenerate its merge with scenes enabled. For playback rules plus launcher Read:

```sh
python3 tools/configure_tvqa.py --base OWN_EXPORT.zip --output generated/tvqa-scenes-merge.zip --scenes --launcher-package com.spocky.projengmenu
```

`com.spocky.projengmenu` is Projectivy Launcher's public package name. Use your own launcher's package if different, or omit `--launcher-package` to omit launcher Read. The generator adds playback-playing → Cinema and playback-paused/stopped → Pause rules for its default media-app list. These rules require the relevant tvQuickActions playback/notification access to be working for those apps.

To select your own playback scope, repeat `--media-app` for each package. Providing these options replaces the default media-app list:

```sh
python3 tools/configure_tvqa.py --base OWN_EXPORT.zip --output generated/tvqa-scenes-custom-merge.zip --scenes --media-app tv.emby.embyatv --media-app com.google.android.youtube.tv
```

For the optional Emby foreground/audio fallback, add `--emby-fallback` to a command that also includes `--scenes`. It adds scoped Emby enter/exit rules for `tv.emby.embyatv`; it is not a general audio detector for every app. Only enable it if you use Emby and need that fallback.

Restore the generated ZIP with **Merge**, never **Overwrite all**. Review existing rules that target the same lights, grant the event permissions needed, and confirm the new event macros are enabled. A generator refusal about a changed community scope means the existing community rule needs review before a fresh export; unrelated rules should be retained.

For a manual button or custom rule, choose an explicit broadcast receiver target with component `dev.huesync.relay/.SceneReceiver`, launch flags `0x20` (include stopped packages), no extras, and one of these actions:

- `dev.huesync.relay.CINEMA`
- `dev.huesync.relay.PAUSE`
- `dev.huesync.relay.READ`
- `dev.huesync.relay.CYCLE`

The generator creates a Cycle intent but does not assign it to a physical button. Bind it to the button gesture you want in tvQuickActions.

## Check and disable scenes

Test with your own lights: a Cinema event during the window; a pause lasting more than three seconds; a brief pause followed by resumed playback; launcher Read with a valid low and high sensor reading; and a manual Cycle outside the window. Confirm the selected app actually emits the event before assuming a Bridge problem. These are suggested live checks for your installation, not claims that this community package has already run on your devices.

To return to core sync only, disable the community scene event macros, set `optionalScenes.enabled` to `false`, regenerate the HTTP import and import the update. Regenerating a core-only tvQuickActions merge does **not** delete scene macros already installed; disable those macros explicitly. Keep the three core lifecycle rules if you still want automatic sync start/stop.
