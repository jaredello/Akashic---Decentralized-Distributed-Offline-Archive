"""macOS disc tools: list burners, make UDF images, burn both discs at once, verify."""

import re
import subprocess
import sys
from pathlib import Path

from .volume import sha256_file


def _need_mac():
    if sys.platform != "darwin":
        raise RuntimeError("Burning uses macOS's built-in drutil/hdiutil and only runs on a Mac.")


def list_drives():
    """Return [(index, description)] for every optical drive macOS can see."""
    _need_mac()
    out = subprocess.run(["drutil", "list"], capture_output=True, text=True).stdout
    drives = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(.+?)\s{2,}", line + "  ")
        if m and not line.strip().lower().startswith("vendor"):
            drives.append((int(m.group(1)), " ".join(line.split()[1:])))
    return drives


def _stream(cmd, log):
    log("$ " + " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        line = line.rstrip()
        if line:
            log(line)
    p.wait()
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} exited with code {p.returncode}")


def make_image(disc_dir, out_iso, volume_name, log=print):
    """Package a staged disc folder into a UDF .iso (works for 100 GB BDXL)."""
    _need_mac()
    out_iso = Path(out_iso)
    if out_iso.exists():
        out_iso.unlink()
    _stream(["hdiutil", "makehybrid", "-udf", "-udf-version", "1.50",
             "-udf-volume-name", volume_name[:30], "-o", str(out_iso), str(disc_dir)], log)
    return out_iso


def burn(path, drive_index, log=print, verify=True):
    """Burn a staged disc folder (as UDF) or a .iso image to the given drive."""
    _need_mac()
    cmd = ["drutil", "-drive", str(drive_index), "burn", "-udf", "-eject"]
    if verify:
        cmd.insert(5, "-verify")
    _stream(cmd + [str(path)], log)


def verify(disc_root, log=print):
    """Check every file on a disc against its SHA256SUMS. Returns (ok, bad)."""
    root = Path(disc_root)
    sums = root / "SHA256SUMS"
    if not sums.exists():
        raise FileNotFoundError(f"No SHA256SUMS on {root}")
    ok = bad = 0
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        p = root / name
        if p.exists() and sha256_file(p) == digest:
            ok += 1
        else:
            bad += 1
            log(f"MISMATCH {name}")
    log(f"Verified {root}: {ok} OK, {bad} bad")
    return ok, bad


def find_discs(base="/Volumes"):
    """Auto-detect mounted DiscKit discs."""
    out = []
    b = Path(base)
    if b.is_dir():
        for p in sorted(b.iterdir()):
            if (p / "DISCKIT.json").exists():
                out.append(p)
    return out
