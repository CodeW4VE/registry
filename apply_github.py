#!/usr/bin/env python3
"""Push the registry metadata to the GitHub repos.

    python3 apply_github.py                    dry run, prints what would change
    python3 apply_github.py --apply            actually does it
    python3 apply_github.py --sync-descriptions  also overwrite descriptions
                                                 that already exist

The registry is the source of truth for topics, description and homepage.
This script only writes those three things plus a LICENSE file when one is
missing. It never touches code, releases or visibility: making a repo public
is a one-way door and stays a manual decision.

Uses the `gh` CLI so it inherits your login. No tokens in here.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.json"

ORG = "CodeW4VE"
MAX_TOPICS = 20  # GitHub's limit

# Extra topics implied by what a piece is, so we do not repeat them by hand
# in every entry of pieces.toml.
TYPE_TOPICS = {
    "fabric-mod": ["minecraft", "minecraft-mod", "fabric", "fabricmc"],
    "mcdr-plugin": ["minecraft", "mcdreforged", "mcdr-plugin"],
    "discord-bot": ["discord", "discord-bot", "self-hosted"],
    "service": ["minecraft", "self-hosted"],
    "library": ["minecraft", "library"],
    "runtime": ["minecraft", "server-management"],
    "tool": ["minecraft", "cli"],
}
SIDE_TOPICS = {"server": ["server-side"], "client": ["client-side"]}

MIT = """MIT License

Copyright (c) 2026 TVTvirus

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def gh(*args, check=True):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        print(f"  ! gh {' '.join(args)}\n    {out.stderr.strip()}", file=sys.stderr)
        return None
    return out.stdout.strip()


def slug_topic(text):
    """GitHub topics: lowercase, alphanumeric and dashes, 50 chars max."""
    text = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return text[:50]


def wanted_topics(piece):
    topics = list(TYPE_TOPICS.get(piece.get("type"), ["minecraft"]))
    topics += SIDE_TOPICS.get(piece.get("side"), [])
    topics += piece.get("tags", [])
    seen, out = set(), []
    for t in (slug_topic(t) for t in topics):
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:MAX_TOPICS]


def wanted_homepage(piece, registry):
    return piece.get("docs") or registry.get("homepage", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sync-descriptions", action="store_true",
                    help="overwrite descriptions that are already set")
    ap.add_argument("--prune-topics", action="store_true",
                    help="also remove topics that are not in the registry. Off by "
                         "default: a topic you added by hand is usually a good one")
    args = ap.parse_args()

    index = json.loads(INDEX.read_text())
    registry = index["registry"]
    changes = 0
    skipped_desc = []

    for pid, piece in sorted(index["pieces"].items()):
        repo = piece.get("repo", "")
        if not repo.startswith(f"{ORG}/"):
            continue  # external pieces and upstreams are not ours to edit

        current = gh("repo", "view", repo, "--json",
                     "description,homepageUrl,repositoryTopics,isPrivate,licenseInfo")
        if not current:
            # Planned pieces have no repo yet, that is expected, not an error.
            print(f"{repo:<34} not created yet")
            continue
        current = json.loads(current)

        now_topics = sorted(t["name"] for t in (current.get("repositoryTopics") or []))
        new_topics = sorted(wanted_topics(piece))
        now_desc = (current.get("description") or "").strip()
        new_desc = piece["summary"].strip()
        now_home = (current.get("homepageUrl") or "").strip()
        new_home = wanted_homepage(piece, registry).strip()

        todo = []
        added = [t for t in new_topics if t not in now_topics]
        removed = [t for t in now_topics if t not in new_topics] \
            if args.prune_topics else []
        if added or removed:
            detail = "+" + ",".join(added) if added else ""
            if removed:
                detail += ("  " if detail else "") + "-" + ",".join(removed)
            todo.append(("topics", detail))
        if not now_desc:
            todo.append(("description", f'"{new_desc}"'))
        elif now_desc != new_desc:
            if args.sync_descriptions:
                todo.append(("description", f'"{now_desc}"\n{" ":>26}-> "{new_desc}"'))
            else:
                skipped_desc.append(repo)
        if now_home != new_home:
            todo.append(("homepage", f"{now_home or '(empty)'} -> {new_home}"))

        needs_license = current.get("licenseInfo") is None
        if needs_license:
            todo.append(("LICENSE", "add MIT (commit to the default branch)"))

        if not todo:
            print(f"{repo:<34} ok")
            continue

        print(f"{repo:<34} {'APPLYING' if args.apply else 'would change'}")
        for what, detail in todo:
            print(f"    {what:<12} {detail}")
        changes += 1

        if not args.apply:
            continue

        cmd = ["repo", "edit", repo]
        if any(w == "topics" for w, _ in todo):
            for t in removed:
                cmd += ["--remove-topic", t]
            for t in added:
                cmd += ["--add-topic", t]
        if any(w == "description" for w, _ in todo):
            cmd += ["--description", new_desc]
        if any(w == "homepage" for w, _ in todo):
            cmd += ["--homepage", new_home]
        if len(cmd) > 3:
            gh(*cmd)
        if needs_license:
            add_license(repo)

    print()
    if skipped_desc:
        print(f"{len(skipped_desc)} repos already have a description and were left "
              f"alone: {', '.join(r.split('/')[1] for r in skipped_desc)}")
        print("   run with --sync-descriptions to replace them with the registry copy\n")
    if args.apply:
        print(f"applied to {changes} repos")
    else:
        print(f"{changes} repos would change. Re-run with --apply to do it.")
    return 0


def add_license(repo):
    """Create LICENSE through the API so the commit is yours, not a bot's."""
    import base64
    content = base64.b64encode(MIT.encode()).decode()
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/LICENSE", "-X", "PUT",
         "-f", "message=Add MIT license",
         "-f", f"content={content}"],
        capture_output=True, text=True)
    if out.returncode != 0:
        print(f"  ! LICENSE on {repo}: {out.stderr.strip()}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
