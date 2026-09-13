# Validation and limitations

Release: 1.1.0 (versionCode 2). The public app is `dev.huesync.relay`. This update adds awake idle checks and service-recreation reconciliation. Its public application identity, callback scheme and shortcut IDs are unchanged; they remain separate from the original private installation. Credentials and setup exports are generated anew for each recipient.

## Offline checks

Run from the extracted package root:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B android/build.py --test-only
```

Python 3.8 or newer and the standard library run the setup-tool tests. The script-behavior checks in `test_config.py` use Node.js on PATH; keep Node available so those checks run rather than skip. The Android checks additionally need a Java JDK. No test contacts a theater device.

Coverage includes:

- Controller wake/boot timing, bounded retries, duplicate-event handling, request serialization, stale replies, sleep compensation and callback timeout.
- Awake idle checks, error/not-ready backoff, bounded recovery escalation, scene serialization and sleep cancellation.
- The actual RelayService runs against offline Android runtime fixtures to exercise sticky/null recreation, interactive-state reconciliation, stale Emby context, persisted pending leases and service shutdown.
- Native Read check/recall ordering, scene supersession, Pause debounce and scoped Emby audio gating.
- Public manifest and shared shortcut IDs, build configuration, signature/alignment verification during APK builds.
- Config validation, certificate pins, authentication headers, selected input, actual JavaScript execution with synthetic responses, optional time/sensor guards and the absence of nested shortcut launches.
- Fake TLS and registration connections: certificate mismatch sends no HTTP request, bounded pending-code retries, private file permissions, refusal to overwrite and sanitized failures.
- tvQuickActions synthetic exports: preservation of unrelated data, noncolliding IDs, idempotent generation, refusal to silently activate disabled saved actions or override constrained rules.
- Release allowlisting and nested archive scanning, planted secret-like fixtures, path traversal, symlinks, expansion limits and checksum verification.

The build process verifies APK signatures, ZIP alignment and package metadata. Release validation should also extract the archive to a clean directory for tests and a fresh build using separately supplied SDK tools and signing key. Historical 1.0.0 build results are recorded in [RELEASE-CHECKS.md](RELEASE-CHECKS.md); they do not verify the 1.1.0 changes. A successful clean build means it does not depend on the private project's source or backups; it does not imply a bit-for-bit reproducible APK across tool versions and build times.

The final 1.1.0 offline run passed 66 root Python tests, 22 Android Python tests (including 13 actual-service fixture tests), 110 controller checks, 40 policy checks and 7 Emby audio checks. Both private and public APK builds passed. Tests and an APK build also passed from a clean extracted source archive. An exact-value audit of 87 known private values found no matches in the checked source archive. These checks do not prove that arbitrary private data could never escape a scanner.

## Recovery checks on the upgraded private installation

On 13 September 2026, the original private package was upgraded to 1.3 with its existing signing key. Its generic behavior sources matched the public recovery implementation. The public 1.1.0 package and newly generated imports remain uninstalled.

| Scenario | Observed result |
| --- | --- |
| Awake idle maintenance | The first healthy Probe ran about 60 seconds after startup checks finished. The next Probe ran about one minute after the first completed. No continuous Start loop was observed. |
| Controlled Hue Stop while awake | The next minute check detected inactive sync and dispatched Start about 15.5 seconds after the controlled Stop; the API reported active about 19.1 seconds after Stop. |
| Simulated helper VM crash | Android scheduled a service restart after one second. The new process received a null restart and reconciled current interactive state. After a test Hue Stop, it probed about 2 seconds after recreation, started about 2.5 seconds after recreation and reported API-active about 6.9 seconds after recreation, without a manual wake or app trigger. |
| Sleep then wake | Sleep dispatched Stop; the API reported inactive about 4.4 seconds later and again after the compensation interval, with four asleep observations remaining inactive. Wake created a new service instance in the same process. The input initially reported zero dimensions; once a Probe reported ready video, Start followed about 0.2 seconds later and API-active about 4 seconds after readiness (about 27 seconds after wake). Active state remained observed for at least another 31 seconds. |
| TiviMate multiview | After the recovery checks, the owner entered and left multiview and confirmed the strip lights kept following. No sync loss or forced recovery during this visual check was established. |

The controlled recovery rows above are API and service observations; the TiviMate multiview row records the separate owner-observed visual result. The simulated crash demonstrates sticky recreation in this run. It does not establish restart timing for every SIGKILL, memory-pressure termination or force-stop. The live sleep occurred about five seconds after startup checks finished, so this cycle verifies normal idle sleep/wake behavior. It does not demonstrate sleep interrupting an in-flight request; those races are covered by offline tests.

## Historical live observations from the original installation

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

Recovery depends on tvQuickActions delivering lifecycle events and HTTP Shortcuts being allowed to run. While awake, the resident service sends one idle Probe after 60 seconds; a valid ready inactive/non-video result opens a bounded 90-second/12-Probe recovery attempt. Healthy, failed or not-ready checks return to idle. Detection can add up to 60 seconds, plus request/readiness delays, and scene or pending-request work can defer it. A resolution/refresh-mode change can trigger an earlier check; an HDR-only transition may not produce that callback. API-active/video status with dark or static lights cannot be detected by maintenance.

`START_STICKY` permits Android to recreate a killed service, but restart timing is not guaranteed. Recreation uses actual interactive state and waits out a valid persisted 45-second pending-request lease. Force-stop suppresses ordinary sticky restart; a later eligible explicit startup event is needed. A manual Hue-app Stop while the relay remains awake may be reversed by maintenance. Explicit relay `SYNC_STOP` cancels maintenance and reconciles off, but does not persist a permanent pause across later process recreation or startup events. Boot still waits 20 seconds from event receipt.

Sleep cancels pending decisions, not an HTTP request already sent to the box. A late Start can momentarily race with sleep; Stop and follow-up off checks compensate. USB power-state detection provides an independent off signal in the documented wiring. Behavior after hard power loss depends on both devices and USB settings.

Optional scene reliability also depends on the media app's playback events. Emby's audio fallback is deliberately limited to its foreground scope. After process recreation a fresh Emby entry event is required; cached foreground context and scenes are not replayed. Read's default fail-open behavior can recall Read if the sensor is unavailable within the allowed time window; configure it to false if that is not wanted.

## A useful live check after your installation

Confirm manual sync, then wake, sleep, boot, an app change, a resolution/frame-rate change and a network interruption/recovery. Check both the Hue status and actual strip behavior. Test optional Cinema/Pause/Read separately. If manual broadcasts work but normal controls do not, inspect the enabled tvQuickActions event mappings before changing HDMI settings.

You can inspect relay-only logs locally with:

```sh
adb logcat -s HueSyncRelay
```

Review any log before sharing it. HTTP Shortcuts entries are excluded from normal history for privacy, so keep your private configuration available when diagnosing authentication or pin errors. Never publish full device/app backups as a diagnostic shortcut.
