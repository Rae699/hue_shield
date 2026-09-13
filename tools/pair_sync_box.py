#!/usr/bin/env python3
"""Pair YOUR Sync Box and save a private local configuration.

The required leaf-certificate SHA-256 pin must be independently verified first.
No discovery or automatic certificate trust is performed. Hold the physical
button for 3 seconds, then release it when prompted. Only pending code 16 retries.
"""
import argparse
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import ssl
import time

from generate_config import host as validate_host, fingerprint as validate_fingerprint, validate as validate_config

WINDOW = 45
MAX_RESPONSE = 8192
BODY = json.dumps({"appName": "HueSyncRelay", "instanceName": "AndroidTV"}).encode("utf-8")


class PairingError(Exception):
    """Only fixed, non-secret diagnostic messages belong here."""


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, device, expected_pin, timeout):
        # This local device's CA chain is replaced ONLY by exact leaf pin trust.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.expected_pin = expected_pin
        super().__init__(device, port=443, timeout=timeout, context=context)

    def connect(self):
        super().connect()
        certificate = self.sock.getpeercert(binary_form=True)
        if not certificate or not hmac.compare_digest(hashlib.sha256(certificate).hexdigest(), self.expected_pin):
            self.close()
            raise PairingError("Certificate mismatch; no registration request was sent.")


def register(device, pin):
    deadline = time.monotonic() + WINDOW
    prompted = False
    while time.monotonic() < deadline:
        connection = PinnedConnection(device, pin, min(5, deadline - time.monotonic()))
        try:
            connection.connect()  # The certificate is checked before request headers or body.
            if time.monotonic() >= deadline:
                break
            connection.sock.settimeout(min(5, deadline - time.monotonic()))
            connection.request("POST", "/api/v1/registrations", body=BODY,
                               headers={"Content-Type": "application/json", "Connection": "close"})
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE or time.monotonic() >= deadline:
                raise PairingError("Pairing response exceeded the size or time limit.")
            reply = json.loads(raw)
            if not isinstance(reply, dict):
                raise PairingError("Unexpected pairing response; no retry was sent.")
            if type(reply.get("code")) is int and reply["code"] == 16:
                if not prompted:
                    print("Hold the Sync Box button for 3 seconds, then release it. Waiting up to 45 seconds.")
                    prompted = True
            elif 200 <= response.status < 300 and ("code" not in reply or
                    (type(reply["code"]) is int and reply["code"] == 0)):
                return reply.get("accessToken")
            else:
                raise PairingError("Registration failed; no retry was sent.")
        finally:
            connection.close()
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(1, remaining))
    raise PairingError("Pairing timed out; no configuration was saved.")


def pair(device, pin, input_number, output):
    normalized = validate_host(device, "host").strip("[]")
    pin = validate_fingerprint(pin, "fingerprint")
    if type(input_number) is not int or input_number not in range(1, 5):
        raise ValueError("Choose HDMI input 1 through 4")
    output = Path(output).expanduser()
    # Reserve the private output before any connection; O_EXCL also rejects symlinks.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            config = {"ownSyncBox": {"host": normalized, "token": register(normalized, pin),
                "certificateFingerprint": pin, "input": input_number}, "optionalScenes": {"enabled": False}}
            validate_config(config)
            json.dump(config, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Your Sync Box hostname or IP, without a URL or port")
    parser.add_argument("--fingerprint", required=True, help="Independently verified 64-hex SHA-256 leaf-certificate fingerprint")
    parser.add_argument("--input", type=int, choices=range(1, 5), default=1, help="HDMI input number (default: 1)")
    parser.add_argument("--output", type=Path, default=Path("config.local.json"), help="New private config file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        output = pair(args.host, args.fingerprint, args.input, args.output)
    except PairingError as error:
        print(str(error))
        return 1
    except (OSError, ValueError, RecursionError, http.client.HTTPException):
        print("Pairing failed. Check the verified certificate pin, device host, network, and a new writable output path.")
        return 1
    except KeyboardInterrupt:
        print("Pairing cancelled; no configuration was saved.")
        return 1
    print("Saved private configuration:", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
