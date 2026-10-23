# DiscKit "Signed Mac App" feature: static checks, stubbed signing harness, kit API/zip contents
import io
import os
import plistlib
import shutil
import subprocess
import zipfile

import pytest
import requests
import yaml

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MAC = "/app/disckit/packaging/macos"
WF = "/app/.github/workflows/disckit-macos.yml"
ST = "/root/signtest"
SECRETS = ["MACOS_CERT_P12_BASE64", "MACOS_CERT_PASSWORD", "ASC_API_KEY_P8_BASE64", "ASC_API_KEY_ID", "ASC_API_ISSUER_ID"]


# --- Static checks
@pytest.mark.parametrize("f", ["build_app.sh", "sign_notarize.sh"])
def test_bash_syntax(f):
    assert subprocess.run(["bash", "-n", f"{MAC}/{f}"]).returncode == 0


def test_workflow_yaml_secrets_and_summary():
    d = yaml.safe_load(open(WF))
    steps = d["jobs"]["build"]["steps"]
    build = [s for s in steps if "build_app.sh" in str(s.get("run", ""))][0]
    for s in SECRETS:
        assert build["env"][s] == "${{ secrets.%s }}" % s
    assert any(s.get("name") == "Build summary" for s in steps)


def test_entitlements_plist():
    p = plistlib.load(open(f"{MAC}/entitlements.plist", "rb"))
    assert p["com.apple.security.cs.allow-unsigned-executable-memory"] is True


def test_signing_guide_sections():
    t = open(f"{MAC}/SIGNING.md").read()
    for k in ["enroll", "Certificate Signing Request".split()[0], "Developer ID Application", "Export 2 items",
              "base64", "Issuer ID", "Key ID", "only be downloaded once", *SECRETS, "Run workflow",
              "spctl", "stapler", "Troubleshooting"]:
        assert k in t, k


def test_build_app_unsigned_fallback_code():
    t = open(f"{MAC}/build_app.sh").read()
    assert "codesign --force --deep --sign - " in t
    assert '"-unsigned"' in t
    assert "FIRST_LAUNCH.txt" in t and "FIRST_LAUNCH_SIGNED.txt" in t
    assert 'notarize "$DMG"' in t and 'codesign --force --timestamp --sign "$IDENTITY" "$DMG"' in t


# --- Stubbed harness
def _prep():
    shutil.rmtree(f"{ST}/X.app", ignore_errors=True)
    shutil.rmtree(f"{ST}/build", ignore_errors=True)
    os.makedirs(f"{ST}/X.app/Contents/MacOS")
    os.makedirs(f"{ST}/build")
    shutil.copy("/root/pyi/dist/DiscKit/DiscKit", f"{ST}/X.app/Contents/MacOS/")
    shutil.copytree("/root/pyi/dist/DiscKit/_internal", f"{ST}/X.app/Contents/Frameworks")
    open(f"{ST}/X.app/Contents/Frameworks/fake.dylib", "wb").write(bytes.fromhex("cffaedfe0c000001") + b"\0" * 24)
    if os.path.exists(f"{ST}/calls"):
        os.remove(f"{ST}/calls")


def _run(status="Accepted"):
    env = dict(os.environ, PATH=f"{ST}/bin:" + os.environ["PATH"], FAKE_STATUS=status)
    for s in SECRETS:
        env.pop(s, None)
    return subprocess.run(["bash", "t.sh"], cwd=ST, env=env, capture_output=True, text=True)


@pytest.mark.skipif(not os.path.isdir(f"{ST}/bin"), reason="harness missing")
def test_harness_accepted():
    _prep()
    r = _run()
    assert r.returncode == 0, r.stderr
    for k in ["disabled without secrets: OK", "enabled with secrets: OK",
              "IDENTITY=Developer ID Application: Test Person (TEAM123456)", "NOTARIZE_OK"]:
        assert k in r.stdout
    calls = open(f"{ST}/calls").read()
    assert "--options runtime --entitlements" in calls and "fake.dylib" in calls
    assert "notarytool submit" in calls and "--key-id K1 --issuer I1" in calls
    assert "stapler staple" in calls and "stapler validate" in calls and "spctl --assess" in calls
    assert not os.path.exists(f"{ST}/build/cert.p12") and not os.path.exists(f"{ST}/build/AuthKey.p8")


@pytest.mark.skipif(not os.path.isdir(f"{ST}/bin"), reason="harness missing")
def test_harness_invalid():
    _prep()
    r = _run("Invalid")
    assert r.returncode != 0
    calls = open(f"{ST}/calls").read()
    assert "notarytool log 1111-2222" in calls and "stapler" not in calls
    assert not os.path.exists(f"{ST}/build/cert.p12") and not os.path.exists(f"{ST}/build/AuthKey.p8")


# --- Backend kit API
def test_kit_info_signing():
    app = requests.get(f"{BASE_URL}/api/kit/info", timeout=30).json()["app"]
    assert app["signing_ready"] is True and app["signed"] is False
    assert app["signing_guide"] == "packaging/macos/SIGNING.md"


def test_kit_zip_signing_files():
    r = requests.get(f"{BASE_URL}/api/kit/download", timeout=60)
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    m = {i.filename: (i.external_attr >> 16) & 0o777 for i in z.infolist()}
    p = "DiscKit/packaging/macos/"
    assert m[p + "sign_notarize.sh"] == 0o755
    for f in ["entitlements.plist", "SIGNING.md", "FIRST_LAUNCH_SIGNED.txt"]:
        assert p + f in m
