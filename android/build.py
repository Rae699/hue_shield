#!/usr/bin/env python3
"""Build the Java-only relay offline using an installed Android SDK and JDK."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT.parent
ANDROID = "{http://schemas.android.com/apk/res/android}"
BUILD_TOOLS_VERSION = "34.0.0"


def resolve_sdk(sdk):
    """Resolve only the documented, installed SDK layout; never download tools."""
    root = Path(sdk).expanduser().resolve()
    jar = root / "platforms" / "android-34" / "android.jar"
    tools = root / "build-tools" / BUILD_TOOLS_VERSION
    if not jar.is_file():
        raise ValueError("Android SDK Platform 34 is required: install platforms/android-34/android.jar")
    for name in ("aapt2", "d8", "zipalign", "apksigner"):
        if not (tools / name).is_file() or not os.access(tools / name, os.X_OK):
            raise ValueError("Android SDK Build Tools 34.0.0 executable is missing: " + name)
    return jar, tools


def validate_keystore(path, package_root=PACKAGE_ROOT):
    """Keys are local build inputs and must never live in the shareable package."""
    key = Path(path).expanduser().resolve()
    try:
        key.relative_to(Path(package_root).resolve())
    except ValueError:
        return key
    raise ValueError("Signing keystore must be outside the shareable package directory")


def password_reference(name):
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("Specify the name of a password environment variable")
    if not os.environ.get(name):
        raise ValueError("Password environment variable is missing or empty: " + name)
    return "env:" + name


def validate_java_version(output):
    match = re.search(r"\bjavac\s+(\d+)(?:\.(\d+))?", output)
    if not match or int(match.group(1)) < 11:
        raise ValueError("Java 11 or newer JDK is required (java, javac and keytool)")


def java_tool(name):
    java_home = os.environ.get("JAVA_HOME")
    path = str(Path(java_home).expanduser() / "bin" / name) if java_home else shutil.which(name)
    if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
        raise ValueError("Java 11 or newer JDK is required; cannot find " + name)
    return path


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def run_tests(java, javac):
    run(sys.executable, "-B", "-m", "unittest", "discover", "-s", ROOT / "tests", "-p", "test_*.py")
    with tempfile.TemporaryDirectory(prefix="hue-relay-tests-") as directory:
        source = ROOT / "src" / "dev" / "huesync" / "relay"
        run(javac, "--release", "8", "-d", directory,
            source / "RelayPolicy.java", source / "NativeController.java", source / "EmbyAudioGate.java",
            *sorted((ROOT / "tests").rglob("*.java")))
        for name in ("RelayPolicyTest", "NativeControllerTest", "EmbyAudioGateTest"):
            run(java, "-cp", directory, "dev.huesync.relay." + name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        epilog="Requires Python 3.8+, a Java 11+ JDK, SDK Platform 34 and Build Tools 34.0.0. No downloads are performed.")
    parser.add_argument("--test-only", action="store_true", help="run Python and pure Java checks; no Android SDK or key needed")
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_SDK_ROOT"), help="installed SDK root (default: ANDROID_SDK_ROOT)")
    parser.add_argument("--keystore", type=Path, help="local signing keystore, outside this package")
    parser.add_argument("--password-env", help="environment variable holding the keystore password")
    parser.add_argument("--key-password-env", help="key password environment variable (defaults to --password-env)")
    parser.add_argument("--alias", default="hue-sync-relay", help="signing key alias (default: hue-sync-relay)")
    parser.add_argument("--generate-key", action="store_true", help="create a new local key at --keystore; refuses to overwrite an existing key")
    parser.add_argument("--output", type=Path, help="APK output path (default: android/build/hue-sync-relay-VERSION.apk)")
    args = parser.parse_args(argv)
    java = java_tool("java")
    javac = java_tool("javac")
    version = subprocess.run([javac, "-version"], capture_output=True, text=True, check=True)
    validate_java_version(version.stdout + version.stderr)
    if args.test_only:
        run_tests(java, javac)
        print("All Android source and build checks passed.")
        return 0
    if not args.sdk:
        raise ValueError("Set ANDROID_SDK_ROOT or pass --sdk with an installed Android SDK")
    if not args.keystore or not args.password_env:
        raise ValueError("Building requires --keystore outside the package and --password-env")
    android_jar, tools = resolve_sdk(args.sdk)
    key = validate_keystore(args.keystore)
    store_password = password_reference(args.password_env)
    key_password_name = args.key_password_env or args.password_env
    key_password = password_reference(key_password_name)
    if args.generate_key and key.exists():
        raise ValueError("--generate-key refuses to overwrite an existing keystore")
    if not args.generate_key and not key.is_file():
        raise ValueError("Signing keystore does not exist; use --generate-key to create a new local key")
    run_tests(java, javac)
    if args.generate_key:
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        run(java_tool("keytool"), "-genkeypair", "-noprompt", "-storetype", "JKS", "-keystore", key,
            "-storepass:env", args.password_env, "-keypass:env", key_password_name,
            "-alias", args.alias, "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-dname", "CN=Hue Sync Relay Community Local Build")
        key.chmod(0o600)
    manifest = ET.parse(ROOT / "AndroidManifest.xml").getroot()
    release = manifest.get(ANDROID + "versionName")
    apk = (args.output or ROOT / "build" / ("hue-sync-relay-" + release + ".apk")).expanduser().resolve()
    apk.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hue-relay-build-") as directory:
        work = Path(directory)
        classes = work / "classes"
        classes.mkdir()
        run(javac, "--release", "8", "-classpath", android_jar, "-d", classes,
            *sorted((ROOT / "src").rglob("*.java")))
        run(tools / "aapt2", "link", "-I", android_jar, "--manifest", ROOT / "AndroidManifest.xml",
            "-o", work / "resources.apk")
        run(tools / "d8", "--release", "--min-api", "26", "--lib", android_jar,
            "--output", work, *sorted(classes.rglob("*.class")))
        with zipfile.ZipFile(work / "resources.apk") as resources:
            with zipfile.ZipFile(work / "unsigned.apk", "w", zipfile.ZIP_DEFLATED) as unsigned:
                for info in resources.infolist():
                    unsigned.writestr(info, resources.read(info.filename))
                unsigned.write(work / "classes.dex", "classes.dex")
        run(tools / "zipalign", "-f", "4", work / "unsigned.apk", work / "aligned.apk")
        run(tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", args.alias,
            "--ks-pass", store_password, "--key-pass", key_password, "--v4-signing-enabled", "false",
            "--out", work / "signed.apk", work / "aligned.apk")
        run(tools / "apksigner", "verify", "--verbose", work / "signed.apk")
        run(tools / "zipalign", "-c", "4", work / "signed.apk")
        run(tools / "aapt2", "dump", "badging", work / "signed.apk")
        shutil.copyfile(work / "signed.apk", apk)
    print("APK:", apk)
    print("SHA256:", hashlib.sha256(apk.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Build failed:", error, file=sys.stderr)
        sys.exit(1)
