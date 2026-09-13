# Credentials, certificates and sharing

Only the unconfigured public release is intended for sharing. Your `config.local.json`, generated HTTP Shortcuts ZIP, tvQuickActions backups, device logs and signing keys stay private. HTTP Shortcuts must store the token to send requests; neither its local data nor its exported files should be treated as an encrypted secret vault. Owner-only file permissions help locally but do not protect a file after you upload or forward it.

The relay contains no device credentials and has no INTERNET permission. It invokes HTTP Shortcuts through explicit Android components. Other apps on the TV can address the exported relay receiver, so use it on a trusted TV installation. Completion callbacks must match the current random request nonce. Android debugging grants broad control of the TV; it is needed for setup/maintenance, not normal operation.

## Verify your device before pairing

The generator and pairing helper require the SHA-256 fingerprint of the **complete leaf certificate in DER form**. It is not a public-key/SPKI hash, token or registration ID. Both use the pin as device authentication instead of ordinary public-CA/hostname verification. A pin is useful only if you first obtained it through a trusted process.

Use an already authenticated record from your own setup, or verify the device certificate chain and identity using Philips' current developer guidance. Obtain the appropriate CA certificate and the expected identity independently of the unverified network connection. Do not assume the Sync Box and Hue Bridge share a CA or identity scheme.

Philips' [Hue HDMI Sync Box API documentation](https://developers.meethue.com/develop/hue-entertainment/hue-hdmi-sync-box-api/) may require a developer account. This release does not bundle an unverified CA file or invent a download URL. If you do not have a trusted pin or the necessary CA and identity information, complete that step first. Merely reading a certificate over your LAN does not authenticate it.

With a CA file and expected DNS identity already verified for your device, the following OpenSSL pattern verifies both before you record a pin. Replace all uppercase placeholders with your own values; `OWN_HOST` is the network address, while `EXPECTED_DEVICE_IDENTITY` is the identity in its certificate:

```sh
openssl s_client -connect OWN_HOST:443 \
  -servername EXPECTED_DEVICE_IDENTITY \
  -CAfile trusted-device-ca.pem \
  -verify_hostname EXPECTED_DEVICE_IDENTITY \
  -verify_return_error -showcerts </dev/null > verified-chain.txt
```

Require successful verification and command completion. If the independently known identity is an IP certificate identity, use OpenSSL's appropriate `-verify_ip` option instead. From that **verified** output, save the first complete `BEGIN CERTIFICATE` through `END CERTIFICATE` block as `own-device-leaf.pem`, then run:

```sh
openssl x509 -in own-device-leaf.pem -noout -sha256 -fingerprint
```

Remove the output label and colons; the result must contain 64 hexadecimal characters. Supply it as `certificateFingerprint`. Do not use `curl -k`, an accept-all-certificates setting, or an unverified `s_client -showcerts` result as proof of identity. These commands are based on the [OpenSSL s_client](https://docs.openssl.org/3.0/man1/openssl-s_client/) and [x509](https://docs.openssl.org/3.0/man1/openssl-x509/) documentation.

## Pair your own Sync Box

`tools/pair_sync_box.py` accepts an independently verified pin and checks it **before sending the registration request**. It posts only an application name and instance name to `/api/v1/registrations`. When prompted, hold the physical box button for about three seconds, then release it. The helper retries only numeric response code 16 for up to 45 seconds. Other errors stop the process.

Registration fields and pending-code handling follow the [reference client implementation](https://github.com/MadMonkey87/InnerCore.Api.HueSync/blob/master/InnerCore.Api.HueSync/HueSyncBoxClient.cs) and its [request model](https://github.com/MadMonkey87/InnerCore.Api.HueSync/blob/master/InnerCore.Api.HueSync/Models/RegistrationRequest.cs); the button timing is also described by [openHAB's Hue Sync binding](https://www.openhab.org/addons/bindings/huesync/#discovery). Firmware behavior can differ. This helper was tested with simulated responses, not every Sync Box firmware.

It reserves a new output file with owner-only permissions before contacting the box, refuses to overwrite existing files or symlinks, and removes an incomplete file on failure. It saves the returned token locally without printing the response or token. A token could still have been registered if the final response/save is interrupted; use your own API administration to remove an unused registration if necessary.

## Generated requests

The HTTP Shortcuts import pins each device's certificate and disables redirects, cookies and accept-all-certificates mode. Sync Box requests use its Bearer token; optional Bridge requests use a separate `hue-application-key`. There is no discovery, cloud relay or credential transmission during offline generation. See [HTTP Shortcuts' certificate documentation](https://http-shortcuts.rmy.ch/advanced#using-self-signed-certificates).

If a device certificate changes, reauthenticate the new certificate before replacing the pin and regenerating your private import. A mismatch is not fixed by removing authentication. Optional Read's `readFailOpen` setting controls whether to recall a scene when its sensor check fails; it never disables certificate checking.

Do not expose the Sync Box, Bridge, VRROOM web interface or Android debugging port to the public internet. Keep configuration files out of cloud/public repositories and disable unused debugging access when setup is complete.

## Source and release integrity

`SHA256SUMS` detects changes relative to the provided file list. It is not an independent signature of the ZIP. Android's APK signature is verified during the build. The signing certificate inside the APK is public; its private key is not distributed. A locally signed build uses your key and cannot update an installed APK signed by a different key.

The release packager rejects unknown files and common credential patterns, including in nested APK data. Its diagnostics identify files and pattern types without printing the matching values. Review any modification yourself: arbitrary passwords or personal prose cannot all be recognized automatically. Never add your configured import to the public package to make setup easier for others.
