#!/usr/bin/env python3
"""Render the GitHub org front page (.github/profile/README.md) from index.json.

    python3 render_profile.py            write profile_README.md next to this file
    python3 render_profile.py --publish  commit it to CodeW4VE/.github

Nothing here is written by hand. If a project is missing from the front page,
it is missing from pieces.toml, and that is where you add it.
"""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.json"
OUTPUT = HERE / "profile_README.md"

DISCORD = "https://discord.gg/keyy8As"
LIVE_MAP = "https://mapmine.w4ve.xyz/"

# Order and headings of the front page. Each section is (title, blurb, filter).
SECTIONS = [
    ("Start here", "One command installs any of the rest.",
     lambda p: p["type"] in ("tool", "runtime")),
    ("Server mods", "Drop the jar in `mods/`. Players install nothing.",
     lambda p: p["type"] == "fabric-mod" and p["side"] in ("server", "both")),
    ("Client mods", "For your own instance.",
     lambda p: p["type"] == "fabric-mod" and p["side"] == "client"),
    ("MCDReforged plugins", "Hot-reloadable, no restart.",
     lambda p: p["type"] == "mcdr-plugin"),
    ("Bots and services", "Things that run next to the server.",
     lambda p: p["type"] in ("discord-bot", "service")),
]


def is_ours(piece):
    # Private repos are skipped: linking them from the front page is a 404
    # for everyone who is not you.
    return (piece.get("origin") in ("w4ve", "fork")
            and piece.get("status") in ("stable", "beta")
            and not piece.get("private"))


def row(piece):
    name = piece["name"]
    url = f"https://github.com/{piece['repo']}" if piece.get("repo") else ""
    label = f"**[{name}]({url})**" if url else f"**{name}**"
    if piece.get("origin") == "fork":
        upstream = piece["upstream"]
        label += f"<br><sub>fork of [{upstream}](https://github.com/{upstream})</sub>"
    text = piece.get("blurb") or piece["summary"]
    version = piece.get("latest") or ""
    return f"| {label} | {text} | {'`' + version + '`' if version else ''} |"


def render(index):
    reg = index["registry"]
    pieces = index["pieces"]
    out = [
        "<div align=\"center\">",
        "",
        f"# {reg['name']}",
        "",
        f"### *{reg['tagline']}*",
        "",
        f"{reg['description']}",
        "",
        f"[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)]({DISCORD})",
        f"[![Live Map](https://img.shields.io/badge/MineWave-live%20map-brightgreen?logo=minecraft&logoColor=white)]({LIVE_MAP})",
        "",
        "</div>",
        "",
        "---",
        "",
    ]

    listed = set()
    for title, note, keep in SECTIONS:
        rows = [p for p in pieces.values() if is_ours(p) and keep(p)]
        rows.sort(key=lambda p: p["name"].lower())
        if not rows:
            continue
        listed.update(p["id"] for p in rows)
        out += [f"## {title}", "", f"*{note}*", "",
                "| Project | What it is | Latest |", "| --- | --- | --- |"]
        out += [row(p) for p in rows]
        out.append("")

    planned = [p for p in pieces.values()
               if p.get("origin") == "w4ve" and p.get("status") == "planned"]
    if planned:
        out += ["## In the works", "",
                "Not released yet. Listed so you know where this is going.", ""]
        out += [f"- **{p['name']}** {chr(8212).join([])}- {p['summary']}"
                for p in sorted(planned, key=lambda p: p["name"].lower())]
        out.append("")

    profiles = index.get("profiles", {})
    if profiles:
        out += ["## Profiles", "",
                "Curated sets, so you do not have to pick fifteen mods one by "
                "one. `w4ve install --profile <name>` and you are done.",
                ""]
        for key, prof in profiles.items():
            count = len(prof.get("pieces", []))
            out.append(f"- **{prof['name']}** (`{key}`, {count} pieces) - "
                       f"{prof['description']}")
        out.append("")

    out += [
        "---",
        "",
        "Built for and running on **MineWave**, our private whitelisted server. ",
        f"Peek at the world on the [live map]({LIVE_MAP}), or come hang out in the "
        f"[Discord]({DISCORD}).",
        "",
        "<sub>One person maintains all of this. Issues get answered when they get "
        "answered.</sub>",
        "",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    index = json.loads(INDEX.read_text())
    text = render(index)
    OUTPUT.write_text(text)
    print(f"wrote {OUTPUT} ({len(text.splitlines())} lines)")

    if not args.publish:
        print("review it, then re-run with --publish")
        return 0

    current = subprocess.run(
        ["gh", "api", "repos/CodeW4VE/.github/contents/profile/README.md",
         "--jq", ".sha"], capture_output=True, text=True)
    cmd = ["gh", "api", "repos/CodeW4VE/.github/contents/profile/README.md",
           "-X", "PUT", "-f", "message=Regenerate front page from the registry",
           "-f", f"content={base64.b64encode(text.encode()).decode()}"]
    if current.returncode == 0 and current.stdout.strip():
        cmd += ["-f", f"sha={current.stdout.strip()}"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        return 1
    print("published to CodeW4VE/.github")
    return 0


if __name__ == "__main__":
    sys.exit(main())
