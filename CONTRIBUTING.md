# Contributing

Keep changes focused and include the concrete behavior before and after the change. For architecture and invariants, read [AGENTS.md](AGENTS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Use synthetic inputs for automated tests. Never commit device exports, real credentials, private IP addresses, device identifiers, logs or signing keys. Share redacted symptoms and version information when reporting a problem; do not post the entire contents of HTTP Shortcuts or a router export.

Before a pull request:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B android/build.py --test-only
python3 tools/package_release.py --source-only
```

Have Node.js and a Java JDK available so the full suite executes. If changing Android runtime code, also build with Platform 34/Build Tools 34.0.0 and a private outside-repository test signing key. Do not label a CI-signed APK as an official update: its throwaway key is for build verification only.

Describe the tests you actually ran and whether the change has live-device evidence. Include any compatibility limits. Do not claim an API status proves the lamps worked. Public contract changes must update Java IDs, generator behavior, tests and documentation together.

For security-sensitive reports, use GitHub's private vulnerability reporting if the repository offers it. Otherwise report a minimal, non-sensitive description first; never include active credentials in a public issue.
