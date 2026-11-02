"""leak_scan.py [--show-names] [--generic=a,b] [--names-not-in=i18n.js,...] <path or image:NAME>... < words : nothing of a real house in the demo's code, image and data.
Looks for home-LAN addresses, real MAC addresses, the old house's name and every word read on stdin
(house_words.py of the real house, through a pipe). Prints where, never what matched; exit 1 on any hit."""
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path

PATTERNS = {
    "home LAN address": re.compile(rb"\b192\.168\.50\.\d{1,3}\b"),
    "MAC address": re.compile(rb"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
    "the real house's name": re.compile(("berl" + "oga|" + "".join(map(chr, (0x431, 0x435, 0x440, 0x43B, 0x43E, 0x433)))).encode(), re.I),
}
PLACEHOLDER_MACS = {":".join([b] * 6).encode() for b in ("00", "ff", "FF")} | {b"00:11:22:33:44:55", b"aa:bb:cc:dd:ee:ff",
                                                                              b"AA:BB:CC:DD:EE:FF"}
PLACEHOLDER_MACS = {m.lower() for m in PLACEHOLDER_MACS}
SHOW = "--show-names" in sys.argv                # a name that leaked is printed (never a secret)
GENERIC = {w.strip().lower().encode() for a in sys.argv[1:] if a.startswith("--generic=") for w in a[10:].split(",")}
SKIP_NAMES = {n for a in sys.argv[1:] if a.startswith("--names-not-in=") for n in a[15:].split(",")}      # files the demo never shows
args = [a for a in sys.argv[1:] if a != "--show-names" and not a.startswith(("--generic=", "--names-not-in="))]
words = []
for ln in sys.stdin.read().splitlines():
    kind, _, w = ln.partition("\t")
    if len(w.strip()) >= 4 and w.strip().lower().encode() not in GENERIC:     # --generic=: plain words the product uses too
        words.append((kind == "name", w.strip().encode()))
hits = 0


def scan(label: str, data: bytes):
    global hits
    low = data.lower()
    for what, rx in PATTERNS.items():
        found = [m.group(0) for m in rx.finditer(data)]
        if what == "MAC address":
            found = [m for m in found if m.replace(b"-", b":").lower() not in PLACEHOLDER_MACS]      # a placeholder in any separator or case
        if found:
            hits += 1
            print(f"LEAK {label}: {what} x{len(found)}")
    skip = label.rsplit("/", 1)[-1] in SKIP_NAMES
    found = [(is_name, w) for is_name, w in words if w.lower() in low and not (skip and is_name)]
    if found:
        hits += 1
        names = sorted({w.decode() for is_name, w in found if is_name}) if SHOW else []
        print(f"LEAK {label}: {len(found)} word(s) of the real house {names if names else ''}")


def scan_tar(label: str, fobj):
    with tarfile.open(fileobj=fobj, mode="r|*") as t:
        for m in t:
            if not m.isfile() or m.size > 20_000_000:
                continue
            data = t.extractfile(m).read()
            if m.name.endswith((".tar", "layer.tar")) or m.name.startswith("blobs/"):
                try:
                    scan_tar(f"{label}:{m.name}", io.BytesIO(data))
                    continue
                except tarfile.TarError:
                    pass
            scan(f"{label}:{m.name}", data)


files = 0
for arg in args:
    if arg.startswith("image:"):
        p = subprocess.run(["docker", "save", arg[6:]], capture_output=True, check=True)
        scan_tar(arg, io.BytesIO(p.stdout))
        files += 1
        continue
    for f in [Path(arg)] if Path(arg).is_file() else Path(arg).rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            scan(str(f), f.read_bytes())
            files += 1
print(f"leak scan: {files} sources, {len(words)} words of the real house, {hits} hit(s)")
sys.exit(1 if hits else 0)
