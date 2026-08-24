#!/usr/bin/env python3
"""Build index.json out of pieces.toml.

    python3 build.py              fetch everything, write index.json
    python3 build.py --offline    only validate pieces.toml, writes nothing
    python3 build.py --check      exit non-zero if the index would change (CI)

Standard library only, on purpose: this has to run on any server without
installing anything first. Same rule as the CLI.

What it does:
  1. reads the curated file (pieces.toml)
  2. asks GitHub and Modrinth for the releases of every piece
  3. writes index.json, which is what the CLI, the docs and the future panel read

What it never does: invent metadata. If a field is wrong in index.json,
the fix belongs in pieces.toml.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "pieces.toml"
OUTPUT = HERE / "index.json"

GITHUB_API = "https://api.github.com"
MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "CodeW4VE/registry (+https://w4ve.xyz)"

# Assets we consider installable. Anything else in a release (sources, sigs)
# is ignored so `w4ve install` never has to guess.
# `.w4ve` is a whole piece rather than a file: the CLI installs it through the
# package path, which is what lets the catalog offer a service, a public route
# and a folder with a ceiling, and not only the half that happens to be a jar.
ASSET_SUFFIXES = (".jar", ".mcdr", ".pyz", ".zip", ".w4ve")

# Only these care which Minecraft they are for. An MCDR plugin or a Discord bot
# does not, and pretending otherwise is how the catalog decided that
# `PrimeBackup-v1.13.1.pyz` was for Minecraft 1.13.
MC_SENSITIVE_TYPES = ("fabric-mod", "library", "datapack", "resource-pack")

# Version numbers inside a file name, the only clue GitHub gives us about
# which Minecraft a jar is for.
VERSION_TOKEN = re.compile(r"\d+\.\d+(?:\.\d+)?")

# How many releases we keep per piece. Our own pieces keep their history;
# external ones keep only what is current, otherwise Fabric API alone drags
# 1200 entries and the index stops being readable (and downloadable).
#
# For external pieces the cut is per Minecraft target, not global. Keeping the
# newest 5 overall meant that once Fabric API moved to 26.2, the catalog had
# nothing installable left for a 1.21 server, which is every server we run.
KEEP_OWN = 20
KEEP_EXTERNAL = 3


# ---------------------------------------------------------------- http helpers

def github_token():
    """Optional. Without it we get 60 requests/hour, which is not enough."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def get_json(url, token=None, missing=None):
    """The JSON at `url`, or `None` when we could not get it.

    `missing` is what a 404 returns. A 404 is an answer -- "there is no such
    thing" -- and a timeout is not. The default makes them the same, because
    most callers only want to know whether they got data; a caller that is
    about to accuse a repository of not existing needs to tell a repository
    that is gone from an afternoon when GitHub was slow."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if token and "github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return missing
        print(f"  ! {url} -> HTTP {err.code}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"  ! {url} -> {err}", file=sys.stderr)
        return None


# A repository that answered "there is no such thing", as opposed to one that
# answered with an empty list of releases. The catalog has to tell them apart:
# the first is a broken promise, the second is a piece that has not shipped yet.
GONE = object()


# ------------------------------------------------------------------- fetchers

# The Fabric convention for a multi-version release: `shapeboard-1.7.0+26.2.jar`.
# What comes after the `+` is the Minecraft version, and it is the only place a
# GitHub release says so, because GitHub has no metadata of its own.
#
# Only what follows a `+` is read, never a loose number in the name. That is the
# lesson `PrimeBackup-v1.13.1.pyz` taught twice: it is a plugin for MCDR, not a
# mod for Minecraft 1.13.
MC_IN_ASSET = re.compile(r"\+(?:mc)?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


def mc_in_asset(name):
    stem = re.sub(r"\.(jar|mcdr|pyz|zip)$", "", name, flags=re.IGNORECASE)
    return sorted({m.group(1) for m in MC_IN_ASSET.finditer(stem)})


def fetch_github(repo, token, mc_aware=False):
    """Releases of a GitHub repo, newest first.

    With `mc_aware`, the Minecraft versions are read off the asset names. A mod
    of ours that ships thirteen jars, one per Minecraft, publishes that fact
    only in the file names; without this the index claimed ShapeBoard had
    nothing for 26.2 while the jar was sitting right there in the release."""
    data = get_json(f"{GITHUB_API}/repos/{repo}/releases?per_page=20", token,
                    missing=GONE)
    if data is GONE:
        # No such repository, or one we cannot see. Either way the catalog is
        # about to hand a reader a link that answers 404, which is worse than
        # having no link at all.
        return GONE
    if not data:
        return []
    releases = []
    for rel in data:
        if rel.get("draft"):
            continue
        files = []
        for a in rel.get("assets", []):
            if not a["name"].lower().endswith(ASSET_SUFFIXES):
                continue
            entry = {
                "name": a["name"],
                "url": a["browser_download_url"],
                "size": a["size"],
            }
            if mc_aware:
                found = mc_in_asset(a["name"])
                if found:
                    entry["minecraft"] = found
            files.append(entry)
        versions = sorted({v for f in files for v in f.get("minecraft", ())})
        entry = {
            "version": rel["tag_name"].lstrip("v"),
            "tag": rel["tag_name"],
            "source": "github",
            "published": rel.get("published_at"),
            "prerelease": rel.get("prerelease", False),
            "files": files,
        }
        if versions:
            entry["minecraft"] = versions
        releases.append(entry)
    return releases


def fetch_modrinth(slug, loader="fabric"):
    """Versions of a Modrinth project, newest first.

    Modrinth publishes sha1 and sha512 for every file, so we get the integrity
    check for free. GitHub assets have no published hash: the CLI computes and
    pins one on first download instead.

    Filtered by loader, otherwise the newest Lithium is a NeoForge jar and the
    CLI happily drops it into a Fabric server.
    """
    versions = get_json(f"{MODRINTH_API}/project/{slug}/version")
    if not versions:
        return []
    releases = []
    for ver in versions:
        loaders = ver.get("loaders", [])
        if loader and loaders and loader not in loaders:
            continue
        files = [
            {
                "name": f["filename"],
                "url": f["url"],
                "size": f.get("size"),
                # Sorted: Modrinth hands the hashes back in whatever order it
                # feels like, and an unsorted copy makes two identical builds
                # differ, which is a --check failure in CI over nothing.
                "hashes": dict(sorted((f.get("hashes") or {}).items())),
                "primary": f.get("primary", False),
            }
            for f in ver.get("files", [])
        ]
        releases.append({
            "version": ver["version_number"],
            "source": "modrinth",
            "published": ver.get("date_published"),
            "prerelease": ver.get("version_type") != "release",
            "minecraft": ver.get("game_versions", []),
            "loaders": ver.get("loaders", []),
            "files": files,
        })
    return releases


def fetch_pypi(package):
    """Releases of a PyPI package. MCDR itself installs with pip, so that is
    where its versions live."""
    data = get_json(f"https://pypi.org/pypi/{package}/json")
    if not data:
        return []
    releases = []
    for version, files in data.get("releases", {}).items():
        wheels = [f for f in files if f["filename"].endswith((".whl", ".tar.gz"))]
        if not wheels:
            continue
        releases.append({
            "version": version,
            "source": "pypi",
            "published": wheels[0].get("upload_time_iso_8601"),
            "prerelease": any(c in version for c in ("a", "b", "rc", "dev")),
            "files": [{"name": w["filename"], "url": w["url"],
                       "size": w.get("size"),
                       "hashes": {"sha256": w.get("digests", {}).get("sha256")}}
                      for w in wheels],
        })
    return releases


def fetch_modrinth_project(slug):
    """Project-level info. `status` matters: a piece stuck in `processing` or
    `withheld` is not actually downloadable by anyone yet.

    Deliberately no download counter: it ticks on its own, so every --check in
    CI would report the index as out of date with nothing having changed. The
    index says how to install a piece, it is not a dashboard."""
    data = get_json(f"{MODRINTH_API}/project/{slug}")
    if not data:
        return None
    return {
        "id": data.get("id"),
        "status": data.get("status"),
        "client_side": data.get("client_side"),
        "server_side": data.get("server_side"),
    }


# ------------------------------------------------------------------ validation

def release_supports(release, mc):
    """Whether a release is installable on a given Minecraft version.

    Modrinth states it. GitHub does not, so we read the file names, which is
    exactly what the CLI does when it picks which jar to download.
    """
    versions = release.get("minecraft")
    if versions:
        return mc in versions
    tokens = [t for f in release.get("files", [])
              for t in VERSION_TOKEN.findall(f["name"])]
    return mc in tokens if tokens else None


def prune_external(releases, targets, keep=KEEP_EXTERNAL):
    """Keep the newest few releases per supported Minecraft version.

    Plus the newest few overall, so pieces that say nothing about versions
    (MCDR plugins, bots) do not disappear from the catalog.
    """
    kept, seen = [], set()

    def identity(release):
        # Not the version number alone: one number can be several releases,
        # one per Minecraft version. See the dedup comment in main().
        return (release["version"], tuple(sorted(release.get("minecraft") or ())))

    def take(release):
        if identity(release) not in seen:
            seen.add(identity(release))
            kept.append(release)

    for target in targets:
        taken = 0
        for release in releases:
            if taken >= keep:
                break
            if release_supports(release, target):
                take(release)
                taken += 1
    for release in releases[:keep]:
        take(release)
    return sorted(kept, key=lambda r: r.get("published") or "", reverse=True)


def conflict_ids(piece):
    """Ids a piece conflicts with, in either notation (see pieces.toml)."""
    return [item if isinstance(item, str) else item.get("with")
            for item in piece.get("conflicts", []) or []]


def validate(pieces, profiles):
    """Cheap checks that catch the mistakes we actually make."""
    problems = []
    ids = set(pieces)

    for pid, piece in pieces.items():
        for ref in list(piece.get("requires", [])) + conflict_ids(piece):
            if ref not in ids:
                problems.append(f"{pid}: unknown piece '{ref}'")
        if piece.get("origin") == "fork" and not piece.get("upstream"):
            problems.append(f"{pid}: fork without `upstream`")
        if piece.get("status") not in {"stable", "beta", "planned", "infra",
                                        "unreleased"}:
            problems.append(f"{pid}: unknown status '{piece.get('status')}'")
        if not piece.get("summary"):
            problems.append(f"{pid}: no summary (it is the catalog copy)")

    for name, profile in profiles.items():
        for ref in profile.get("pieces", []):
            if ref not in ids:
                problems.append(f"profile {name}: unknown piece '{ref}'")
                continue
            # A profile that forgets a dependency is a broken install.
            for dep in pieces[ref].get("requires", []):
                if dep not in profile.get("pieces", []):
                    problems.append(
                        f"profile {name}: '{ref}' needs '{dep}', not in profile")
        # Two pieces that are known to fight should never share a profile.
        # Only the version-less declarations are checked here: which exact
        # versions a profile ends up with is a question for `w4ve install`.
        for ref in profile.get("pieces", []):
            for item in pieces.get(ref, {}).get("conflicts", []) or []:
                if isinstance(item, str) and item in profile.get("pieces", []):
                    problems.append(
                        f"profile {name}: '{ref}' conflicts with '{item}'")
    return problems


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="validate only, do not hit the network")
    ap.add_argument("--check", action="store_true",
                    help="fail if index.json is out of date")
    args = ap.parse_args()

    # --check compares against a freshly fetched index. With --offline there are
    # no releases to compare, so every piece looks empty and a perfectly good
    # index.json is reported as out of date. They are not combinable.
    if args.check and args.offline:
        ap.error("--check needs the network, it cannot be used with --offline")

    with SOURCE.open("rb") as fh:
        data = tomllib.load(fh)

    pieces = data.get("pieces", {})
    profiles = data.get("profiles", {})
    mc_targets = data["registry"].get("mc_targets", [])

    problems = validate(pieces, profiles)
    if problems:
        print("Problems in pieces.toml:")
        for line in problems:
            print(f"  - {line}")
        print()

    token = None if args.offline else github_token()
    if not args.offline and not token:
        print("note: no GitHub token, running on the 60 req/hour limit\n")

    out_pieces = {}
    unreachable = {}
    for pid, piece in sorted(pieces.items()):
        entry = dict(piece)
        entry["id"] = pid
        entry.setdefault("requires", [])
        entry.setdefault("conflicts", [])
        entry.setdefault("tags", [])
        releases = []

        if not args.offline:
            if piece.get("modrinth"):
                project = fetch_modrinth_project(piece["modrinth"])
                if project:
                    entry["modrinth_info"] = project
                releases += fetch_modrinth(
                    piece["modrinth"],
                    loader="fabric" if piece.get("type") == "fabric-mod" else None)
            if piece.get("repo") and not piece.get("private"):
                found = fetch_github(
                    piece["repo"], token,
                    mc_aware=piece.get("type") in MC_SENSITIVE_TYPES)
                if found is GONE:
                    unreachable[pid] = piece["repo"]
                else:
                    releases += found
            if piece.get("pypi"):
                releases += fetch_pypi(piece["pypi"])

        # The same version usually exists in both places. Keep one copy, from
        # the preferred source (see [registry].sources), then newest first.
        #
        # But "same version" is not the same as "same number". Some mods ship
        # one release per Minecraft version under the SAME number: Server
        # Waypoint has three separate 3.0.3 releases, for 1.21, 26.1 and 26.2.
        # Keying on the number alone kept one of them and threw the rest away,
        # so the catalog swore there was nothing installable on 1.21 while the
        # smp was running exactly that. The Minecraft versions are part of the
        # identity of a release.
        order = {name: i for i, name in
                 enumerate(data["registry"].get("sources", ["modrinth", "github"]))}
        releases.sort(key=lambda r: order.get(r["source"], 99))
        deduped = {}
        for rel in releases:
            key = (rel["version"].lstrip("v"),
                   tuple(sorted(rel.get("minecraft") or ())))
            deduped.setdefault(key, rel)
        # A release that says nothing about Minecraft is the same build as one
        # that does, published in a place with less metadata (a GitHub release
        # next to the Modrinth one). Drop the silent copy, keep the one that
        # tells us something.
        described = {v for v, mc in deduped if mc}
        releases = [rel for (v, mc), rel in deduped.items()
                    if mc or v not in described]
        releases = sorted(releases,
                          key=lambda r: r.get("published") or "", reverse=True)

        if piece.get("origin") == "external":
            releases = prune_external(releases, mc_targets)
        else:
            releases = releases[:KEEP_OWN]
        entry["releases"] = releases
        stable = [r for r in releases if not r["prerelease"]]
        entry["latest"] = (stable or releases or [{}])[0].get("version")
        out_pieces[pid] = entry

        flag = ""
        info = entry.get("modrinth_info") or {}
        if info.get("status") and info["status"] != "approved":
            flag = f"  [modrinth: {info['status']}]"
        if pid in unreachable:
            flag += f"  [{unreachable[pid]} does not answer]"
        if not releases and piece.get("status") in ("stable",):
            flag += "  [no downloadable release]"
        print(f"{pid:<22} {entry.get('latest') or '-':<10} "
              f"{len(releases)} rel{flag}")

    # A catalog is read by a program, so a piece that says `stable` is a promise
    # that `w4ve install` can carry it out. Twice now the catalog has promised
    # something that did not exist -- RconHush, listed as installable while it
    # was only a folder on one laptop, and the WaveChat server, listed as stable
    # against a repository that answers 404. Both were found by a person
    # noticing, which is not a mechanism. This is the mechanism.
    #
    # `planned`, `unreleased` and `infra` are exempt: saying "this is not ready"
    # is the honest thing those states exist for.
    PUBLISHED = {"stable", "beta"}
    broken = []
    for pid, entry in sorted(out_pieces.items()):
        if entry.get("status") not in PUBLISHED:
            continue
        if pid in unreachable:
            broken.append(f"{pid}: `{unreachable[pid]}` does not exist or is "
                          f"private, but the piece is `{entry['status']}`")
        elif not entry.get("releases"):
            broken.append(f"{pid}: `{entry['status']}` with nothing to download "
                          f"(mark it `unreleased` until there is)")
    if broken:
        print("\nThe catalog is promising what it cannot deliver:")
        for line in broken:
            print(f"  - {line}")
        problems += broken

    index = {
        "schema": data.get("schema", 1),
        "registry": data["registry"],
        "pieces": out_pieces,
        "profiles": profiles,
    }

    rendered = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != rendered:
            print("\nindex.json is out of date, run build.py")
            return 1
        print("\nindex.json is up to date")
        return 0

    if args.offline:
        # --offline is for validating pieces.toml, not for publishing an index
        # with every release stripped out of it.
        print("\noffline: validated only, index.json left untouched")
        return 1 if problems else 0

    OUTPUT.write_text(rendered)
    print(f"\nwrote {OUTPUT} ({len(rendered)} bytes, {len(out_pieces)} pieces, "
          f"{len(profiles)} profiles)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
