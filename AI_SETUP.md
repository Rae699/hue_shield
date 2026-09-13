# Set up this project with an AI assistant

This guide is an entry point for an assistant that has never seen the original project conversation. It explains what to learn, which tools to use and how to establish success. Manual instructions are in [docs/SETUP.md](docs/SETUP.md).

## 1. Understand this installation

Read [AGENTS.md](AGENTS.md), [architecture](docs/ARCHITECTURE.md), [setup](docs/SETUP.md), [certificate guidance](docs/SECURITY.md) and [limitations](docs/TESTING.md).

Inspect existing non-secret configuration when access is authorized. Establish only the missing facts:

- Android TV/player model and Android version; installed HTTP Shortcuts and tvQuickActions versions.
- Actual HDMI path, Hue model and input number, whether Hue OUT is connected, and USB power-state behavior.
- Whether manually starting Hue sync produces lights that visibly follow the video.
- Whether core strip sync alone is wanted, or optional room scenes as well.
- Available local computer tools and authorized Android access.

Do not assume that a box named Shield in the Hue app identifies a TV HDMI port: the configured input is the **Hue box's** input. A copied video feed is separate from the TV's selected input. There is no need to change TV inputs merely to trigger the helper.

## 2. Prepare locally

Use the recipient's clone of this source repository. Check `python3`, `node`, the Java JDK and the Android SDK prerequisites in [BUILDING.md](android/BUILDING.md). If only advice is possible, provide the next concrete manual action rather than claiming a tool ran.

Start with `optionalScenes.enabled: false`. Create a private configuration outside the clone, or in a gitignored local path, using [config.example.json](config.example.json). Fill in the user's own host, configured Hue input, token and independently verified leaf-certificate fingerprint. Never request a token pasted into a chat or issue.

If a token is missing, the supplied pairing tool can register one after certificate verification:

```sh
python3 tools/pair_sync_box.py --host OWN_HOST --fingerprint VERIFIED64HEX --input 1 --output /path/to/private/config.local.json
python3 tools/generate_config.py /path/to/private/config.local.json
```

The uppercase text and path are placeholders, not runnable default device details. The physical pairing-button step needs the device owner's participation. The generator itself is offline and writes a credential-containing private ZIP beside the configuration. Preserve file permissions and transfer it privately.

Build the app using an outside-repository key, following BUILDING.md. This repo supplies source, not a ready installed app. Do not reuse or invent the original project's private signing key. A differently signed APK cannot update over an existing package with another signer.

## 3. Configure the existing apps

Install the locally built relay on the authorized Android TV and import the generated entries into HTTP Shortcuts. All nine public shortcut records must retain the IDs in [contract.json](contract.json), even when scene helpers are disabled. They can be hidden in the regular grid.

Export tvQuickActions freshly and use:

```sh
python3 tools/configure_tvqa.py --base OWN_EXPORT.zip --output /path/to/private/tvqa-merge.zip
```

Review the resulting events and restore with **Merge**. Preserve unrelated actions. Resolve a rejected constrained/disabled lifecycle rule in the app with the user rather than forcing the generator through. The required event mappings are:

| Event | Broadcast action |
| --- | --- |
| Screen on | `dev.huesync.relay.SYNC_START` |
| Screen off | `dev.huesync.relay.SYNC_STOP` |
| Power on/boot | `dev.huesync.relay.SYNC_BOOT` |

The target is an explicit broadcast receiver, `dev.huesync.relay/.SceneReceiver`, not an activity. The setup guide covers flags and permissions. Review previous Hue-specific rules to avoid competing commands; do not disable every automation indiscriminately.

## 4. Verify core behavior first

Check a manual relay Start event with actual supported video, then sleep/wake and reboot. Allow for boot-event delivery and the bounded readiness window. Use both local relay logs and a visual confirmation of the strip. Record what actually passed.

If direct relay events work but normal power controls do not, inspect enabled tvQuickActions events. If requests fail, check local reachability, selected input and authenticated certificate/token configuration. If Hue reports active yet the strip shows a static dark color, inspect actual video and entertainment-area behavior; do not claim the controller fixed it based on an API flag.

Stop retrying once the configured window expires. A later event can open a new window. Do not add infinite polling or start a new background process after every app change.

## 5. Add scenes only when requested

Follow [SCENES.md](docs/SCENES.md). Use the recipient's own Bridge key, verified Bridge certificate, existing v2 scene resource UUIDs and light-level resource UUID. These are separate from Sync Box credentials. Check local time and sensor guards. The field `luxThreshold` means raw Hue `light_level`, not physical lux.

Generic scenes need useful media playback events. The optional Emby fallback is scoped to Emby foreground context. TiviMate scene support was not established, and Silo was not tested in the original installation. Test each requested app rather than generalizing from Moonfin or YouTube.

## Completion report

Tell the user what was configured, which visible checks passed, what remains unverified, where their private backups/config live, and how to undo the specific rules. Do not include tokens, keys or full API responses. Runtime operation does not require the computer, AI session or Android network debugging to stay connected.
