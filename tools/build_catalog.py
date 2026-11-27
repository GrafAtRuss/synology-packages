#!/usr/bin/env python3
"""Собрать packages.json из последних релизов репозиториев в sources.json."""
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.json"
OUT = ROOT / "packages.json"
ICONS = ROOT / "icons"


def sh(cmd):
    return subprocess.check_output(cmd, text=True)


def parse_info(text):
    data = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def latest_spk(repo):
    raw = sh(["gh", "release", "view", "--repo", repo, "--json", "tagName,assets"])
    release = json.loads(raw)
    assets = [a for a in release.get("assets") or [] if a.get("name", "").endswith(".spk")]
    if not assets:
        raise SystemExit("в последнем релизе %s нет файла .spk" % repo)
    asset = assets[0]
    return release["tagName"], asset["name"], asset["url"]


def download(url, dest):
    subprocess.check_call(["curl", "-fsSL", "-L", "-o", str(dest), url])


def main():
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    packages = []
    ICONS.mkdir(exist_ok=True)
    tmp = Path("/tmp/spk-catalog")
    tmp.mkdir(exist_ok=True)
    for src in sources:
        repo = src["repo"]
        tag, name, api_url = latest_spk(repo)
        dest = tmp / name
        # gh api follows the asset redirect to the binary
        subprocess.check_call(["gh", "release", "download", tag, "--repo", repo, "--pattern", name, "--clobber", "-D", str(tmp)])
        blob = dest.read_bytes()
        digest = hashlib.md5(blob).hexdigest()
        info = {}
        icon256 = None
        with tarfile.open(dest, "r:") as tar:
            info = parse_info(tar.extractfile("INFO").read().decode("utf-8", "replace"))
            try:
                icon256 = tar.extractfile("PACKAGE_ICON_256.PNG").read()
            except Exception:
                icon256 = None
        pkg = info.get("package") or name.split("-")[0]
        if icon256:
            (ICONS / ("%s_256.png" % pkg)).write_bytes(icon256)
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(icon256)).convert("RGBA").resize((72, 72))
                im.save(ICONS / ("%s_72.png" % pkg))
            except Exception:
                (ICONS / ("%s_72.png" % pkg)).write_bytes(icon256)
        base = "https://raw.githubusercontent.com/GrafAtRuss/synology-packages/main/icons"
        spk_dir = ROOT / "spk"
        spk_dir.mkdir(exist_ok=True)
        vendored = spk_dir / name
        vendored.write_bytes(dest.read_bytes())
        # Прямая отдача без переадресации GitHub Releases: DSM иначе сохраняет пустой ответ.
        link = "https://media.githubusercontent.com/media/GrafAtRuss/synology-packages/main/spk/" + name
        packages.append({
            "package": pkg,
            "version": info.get("version") or tag.lstrip("v"),
            "dname": info.get("displayname") or pkg,
            "desc": info.get("description") or src.get("title") or pkg,
            "changelog": "Релиз %s" % tag,
            "link": link,
            "md5": digest,
            "size": len(blob),
            "maintainer": info.get("maintainer") or "Ермаков Алексей Сергеевич",
            "maintainer_url": info.get("maintainer_url") or "https://ип-ермаков.рф",
            "distributor": info.get("distributor") or "ИП Ермаков А.С.",
            "distributor_url": info.get("maintainer_url") or "https://ип-ермаков.рф",
            "startable": "yes" if info.get("startable", "yes") != "no" else "no",
            "qinst": False,
            "qstart": True,
            "qupgrade": True,
            "deppkgs": None,
            "conflictpkgs": None,
            "snapshot": [],
            "thumbnail": ["%s/%s_72.png" % (base, pkg), "%s/%s_256.png" % (base, pkg)],
            "thumbnail_retina": ["%s/%s_256.png" % (base, pkg), "%s/%s_256.png" % (base, pkg)],
        })
    OUT.write_text(json.dumps({"packages": packages}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("packages", len(packages))


if __name__ == "__main__":
    main()
