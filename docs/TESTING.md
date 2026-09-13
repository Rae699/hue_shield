# Validation and limitations

Release: 1.0.0. The public app is `dev.huesync.relay`. Its controller policy is carried over from the earlier working installation, with a separate application identity, callback scheme and shortcut IDs. Credentials and setup exports are generated anew for each recipient.

## Offline checks

Run from the extracted package root:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B android/build.py --test-only
```

Python 3.8 or newer and the standard library run the setup-tool tests. The script-behavior checks in `test_config.py` use Node.js on PATH; keep Node available so those checks run rather than skip. The Android checks additionally need a Java JDK. No test contacts a theater device.

Coverage includes:

- Controller wake/boot timing, bounded retries, duplicate-event handling, request serialization, stale replies, sleep compensation and callback timeout.
- Native Read check/recall ordering, scene supersession, Pause debounce and scoped Emby audio gating.
- Public manifest and shared shortcut IDs, build configuration, signature/alignment verification during APK builds.
- Config validation, certificate pins, authentication headers, selected input, actual JavaScript execution with synthetic responses, optional time/sensor guards and the absence of nested shortcut launches.
- Fake TLS and registration connections: certificate mismatch sends no HTTP request, bounded pending-code retries, private file permissions, refusal to overwrite and sanitized failures.
- tvQuickActions synthetic exports: preservation of unrelated data, noncolliding IDs, idempotent generation, refusal to silently activate disabled saved actions or override constrained rules.
- Release allowlisting and nested archive scanning, planted secret-like fixtures, path traversal, symlinks, expansion limits and checksum verification.

The signed APK is built from the included public Java source. The build verifies its Android signature, ZIP alignment and package metadata. The release is also extracted to a clean directory for the tests and a fresh build using separately supplied SDK tools and signing key. A successful clean build means it does not depend on the private project's source or backups; it does not imply a bit-for-bit reproducible APK across tool versions and build times.

## What was tested live before this public release

These observations belong to the **earlier original installation**, using SHIELD Android 11, HTTP Shortcuts 4.6 and tvQuickActions 3.7:

| Scenario | Observed result |
| --- | --- |
| Sleep then wake | User confirmed strip off, then visibly following the screen. |
| Reboot | User confirmed sync resumed without starting it manually. One measured run took roughly 106 seconds from reboot initiation; event delivery and device readiness contributed. |
| Emby playback and pause | User confirmed strip sync and room scenes, including a later check launched from Home. |
| YouTube | User confirmed strip sync and room scenes. |
| TiviMate | User confirmed strip sync; room-scene switching did not work and was not pursued. |
| Moonfin | Used throughout diagnosis. Later event/HDR recovery evidence came from logs; no separate final visual confirmation for that batch. |
| Silo | Excluded from live verification because server access was unavailable. |

**The community APK, its fresh HTTP Shortcuts import and tvQuickActions merge have not been installed on that theater.** Offline schema/source checks and earlier live observations are not a substitute for checking the recipient's own import and devices. Android versions beyond the original environment may impose different service or permission behavior. The manifest's minimum API is not a compatibility guarantee.

## What this cannot guarantee

The relay cannot repair an invalid HDMI picture, incompatible HDCP chain, cable failure or unavailable Hue entertainment area. Ready/API-active status does not prove the lamps visibly follow video. Test manual syncing first and verify the lights visually after setup.

Recovery depends on tvQuickActions delivering lifecycle events, HTTP Shortcuts being allowed to run, the service remaining alive and the box becoming reachable within a bounded window. A resolution/refresh-mode change can trigger a check; an HDR-only transition may not produce a display-mode callback. There is no permanent status polling after the recovery window ends. A killed service or a fault outside a window can require a new wake/playback event or an explicit Start broadcast.

Sleep cancels pending decisions, not an HTTP request already sent to the box. A late Start can momentarily race with sleep; Stop and follow-up off checks compensate. USB power-state detection provides an independent off signal in the documented wiring. Behavior after hard power loss depends on both devices and USB settings.

Optional scene reliability also depends on the media app's playback events. Emby's audio fallback is deliberately limited to its foreground scope. Read's default fail-open behavior can recall Read if the sensor is unavailable within the allowed time window; configure it to false if that is not wanted.

## A useful live check after your installation

Confirm manual sync, then wake, sleep, boot, an app change, a resolution/frame-rate change and a network interruption/recovery. Check both the Hue status and actual strip behavior. Test optional Cinema/Pause/Read separately. If manual broadcasts work but normal controls do not, inspect the enabled tvQuickActions event mappings before changing HDMI settings.

You can inspect relay-only logs locally with:

```sh
adb logcat -s HueSyncRelay
```

Review any log before sharing it. HTTP Shortcuts entries are excluded from normal history for privacy, so keep your private configuration available when diagnosing authentication or pin errors. Never publish full device/app backups as a diagnostic shortcut.
