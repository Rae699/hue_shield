# Hue Sync Relay

Automatic Hue HDMI Sync Box start/stop for Android TV setups where the box wakes to **Ready** but does not reliably begin light syncing. The original setup used an NVIDIA SHIELD, HDFury VRROOM and Hue Sync Box 8K.

The helper waits for supported video before starting sync, serializes commands, checks again after detected display-mode changes, and stops sync on sleep. Version 1.1.0 also checks status once per idle minute while awake and reconciles the actual TV state when Android recreates the service. It runs locally on the TV through **tvQuickActions + HTTP Shortcuts**. No AI service or computer is needed during normal operation.

**Full source code is here.** The Android helper includes optional room scenes. It must be built into an Android app; these Java files cannot be pasted into HTTP Shortcuts. The core HTTP requests themselves are only status, start and stop.

## Start with your AI assistant

Give your assistant the repository link and this prompt:

> Help me set up Hue Sync Relay using this repository. Read AGENTS.md and AI_SETUP.md first, then inspect my existing setup before changing anything. Start with core strip sync. Keep credentials in local private files, preserve unrelated automations, and verify the lights visually. Explain any missing prerequisite and use the supplied build, pairing and configuration tools. Do not assume my devices match the original installation.

An assistant with only web access can explain the setup. Building, generating files or controlling your Android TV requires appropriate local tools and access. It must not claim to have changed your devices when it has only read the repository.

| I want to… | Read |
| --- | --- |
| Set it up with an AI | [AI_SETUP.md](AI_SETUP.md) |
| Follow the manual installation | [Setup guide](docs/SETUP.md) |
| Read or build the Android code | [Build guide](android/BUILDING.md) |
| Understand the controller | [Architecture](docs/ARCHITECTURE.md) |
| Add Cinema/Pause/Read scenes | [Optional scenes](docs/SCENES.md) |
| Understand certificates and private files | [Security guide](docs/SECURITY.md) |
| Check what was actually tested | [Testing and limitations](docs/TESTING.md) |

## Wiring used by the original setup

```text
SHIELD -> VRROOM IN0
           TX0 -> TV main HDMI input
           TX1 -> Hue Sync Box HDMI input (same SHIELD picture)
           eARC AUDIO -> compatible sound system
Hue HDMI OUT -> empty
SHIELD USB -> Hue power-state sensing; Hue power adapter stays connected
```

On that setup, SHIELD USB power was off during sleep, Hue USB power-state detection was on, and Hue CEC power detection/inactivity detection were off. This is a starting point to verify on your devices. First confirm **manual light sync works**. The helper does not fix a black HDMI picture, an incompatible HDCP chain or a bad cable, and it does not change VRROOM/TV picture, sound or EDID settings.

## What runs where

- **tvQuickActions:** sends wake, boot, sleep and optional playback events.
- **Android helper:** decides when to check/start/stop; handles timing and stale replies. No INTERNET permission and no device tokens.
- **HTTP Shortcuts:** makes HTTPS requests using your own local device configuration and verified certificate pin.
- **Hue Sync Box:** samples the video and streams to your Hue entertainment area.

The full configuration reserves nine shortcut records. Core sync uses three hidden helpers; optional scenes use the remaining roles. Seeing only a few visible shortcut buttons does not show all background operations.

## Development

Python 3.8+, Node.js and a Java JDK are needed for the complete offline checks. APK builds additionally require Android SDK Platform 34 and Build Tools 34.0.0; see the build guide for signing with your own key.

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B android/build.py --test-only
```

[contract.json](contract.json) defines the public package, actions, shortcut IDs and nonce key. [config.example.json](config.example.json) contains placeholders only. The local generators create personalized imports; never commit or attach those imports, your real configuration or your signing key.

The 1.1.0 recovery changes passed offline tests and builds. Matching behavior on the upgraded original private installation recovered API sync after a controlled Hue Stop and a simulated helper crash, and completed an API-verified sleep/wake cycle; the owner then confirmed the strip kept following while entering and leaving TiviMate multiview. The public package has not been installed. Sleep/wake, reboot and several media apps were tested on the earlier original installation; this does not establish compatibility with every device or make every media app emit useful scene events. See the testing guide for exact boundaries.

An idle check may add up to 60 seconds before detecting a fault, plus request/readiness delays. Android controls service restart timing; force-stop needs a later explicit startup event. API-active but visibly dark lights cannot be diagnosed from the status flags alone. See the testing guide for manual Stop behavior and other limits.

Contributions are welcome: [CONTRIBUTING.md](CONTRIBUTING.md). Independent community project, not endorsed by Philips Hue, NVIDIA or HDFury. Code is [MIT licensed](LICENSE); see [NOTICE](NOTICE) for references.
