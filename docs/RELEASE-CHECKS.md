# Community 1.0.0 release checks

Validation performed on 13 September 2026:

- 49 setup, configuration, pairing and release Python tests passed.
- 9 Android contract/build Python tests passed.
- 92 Java checks passed: 40 relay policy, 45 native controller and 7 Emby audio checks.
- The public source built successfully with Platform 34 and Build Tools 34.0.0. APK v2/v3 signatures and ZIP alignment verified.
- A second build from a clean extracted release produced identical compiled code (`classes.dex`), Android manifest and resources to the distributed APK. APK container hashes may differ with build timestamps.
- Clean-extract tests passed. Both setup generators ran from the extracted package using synthetic configuration/export files; tvQuickActions core and optional-scene modes both completed.
- All public archive members passed the allowlist and nested-content scanner. A separate audit checked known private credentials, device identities and original configuration identifiers against the ZIP and nested APK without finding a match.
- Every archived file is covered by `SHA256SUMS`, except that checksum manifest itself.

Distributed APK SHA-256:

```text
8bfbc07a5a705d74a61c62dc434fb574e48b3ad005165f214d56c2617db7b51e
```

These are build/offline results. This public APK and newly generated imports were not installed on a theater during release preparation. Live behavior still needs verification on the recipient's devices; see [TESTING.md](TESTING.md).
