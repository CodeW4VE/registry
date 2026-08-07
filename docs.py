#!/usr/bin/env python3
"""Build docs.w4ve.xyz out of index.json and the CLI itself.

    python3 docs.py                 write the site into site/
    python3 docs.py --cli PATH      use that w4ve.py for the command reference
    python3 docs.py --serve         build, then serve it on http://localhost:8080

Nothing here is written by hand twice. The page of a piece comes from the
catalog, and the command reference comes from asking the CLI for its own help,
so neither can drift from what is really published. If a page says something
wrong, the fix belongs in pieces.toml or in the CLI's own help text.

Standard library only, same rule as the rest of the repo.
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.json"
OUT = HERE / "site"

CLI_RELEASE = "https://github.com/CodeW4VE/w4ve/releases/latest/download/w4ve.py"
COMMANDS = ["init", "adopt", "list", "search", "info", "profiles", "install",
            "update", "remove", "sync", "status", "doctor"]

TYPE_LABEL = {
    "tool": "Tool",
    "runtime": "Runtime",
    "fabric-mod": "Fabric mod",
    "mcdr-plugin": "MCDReforged plugin",
    "library": "Library",
    "discord-bot": "Discord bot",
    "service": "Service",
}
# Order the catalog is presented in, most useful first.
TYPE_ORDER = ["tool", "runtime", "fabric-mod", "mcdr-plugin", "library",
              "discord-bot", "service"]

SIDE_LABEL = {
    "server": "Server side. Players install nothing.",
    "client": "Client side. Goes in your own instance.",
    "both": "Both sides. Server and client each need it.",
    "standalone": "Runs on its own, next to the server.",
}


# --------------------------------------------------------------------- styling

CSS = """
:root {
  --bg: #fbfaf8; --fg: #1a1a19; --muted: #6b6a66; --line: #e2e0da;
  --card: #ffffff; --accent: #1f6f4a; --accent-soft: #eaf3ee;
  --code-bg: #f3f1ec; --warn-bg: #fdf3e3; --warn-line: #e3c48a;
}
:root:not([data-theme="light"]) { }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14140f; --fg: #e8e6df; --muted: #9c9a92; --line: #2e2e27;
    --card: #1b1b16; --accent: #6cc79a; --accent-soft: #1d2b23;
    --code-bg: #201f1a; --warn-bg: #2a2317; --warn-line: #6a5730;
  }
}
:root[data-theme="dark"] {
  --bg: #14140f; --fg: #e8e6df; --muted: #9c9a92; --line: #2e2e27;
  --card: #1b1b16; --accent: #6cc79a; --accent-soft: #1d2b23;
  --code-bg: #201f1a; --warn-bg: #2a2317; --warn-line: #6a5730;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 60rem; margin: 0 auto; padding: 0 1.25rem 5rem; }

header.top { border-bottom: 1px solid var(--line); margin-bottom: 2.5rem; }
header.top .wrap { padding-top: 1.1rem; padding-bottom: 1.1rem;
  display: flex; gap: 1.5rem; align-items: baseline; flex-wrap: wrap; }
header.top a.brand { font-weight: 700; font-size: 1.05rem; letter-spacing: .02em;
  color: var(--fg); text-decoration: none; }
header.top nav { display: flex; gap: 1.1rem; flex-wrap: wrap; }
header.top nav a { color: var(--muted); text-decoration: none; font-size: .93rem; }
header.top nav a:hover, header.top nav a[aria-current] { color: var(--accent); }

h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 .4rem; letter-spacing: -.01em; }
h2 { font-size: 1.3rem; margin: 2.6rem 0 .8rem; letter-spacing: -.005em; }
h3 { font-size: 1.02rem; margin: 1.8rem 0 .5rem; }
p { margin: 0 0 1rem; }
a { color: var(--accent); }
.lede { font-size: 1.12rem; color: var(--muted); margin-bottom: 2rem; }
.muted { color: var(--muted); }

code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
code { background: var(--code-bg); padding: .12em .38em; border-radius: 4px;
  font-size: .88em; }
pre { background: var(--code-bg); border: 1px solid var(--line); border-radius: 8px;
  padding: .9rem 1rem; overflow-x: auto; font-size: .87rem; line-height: 1.55; }
pre code { background: none; padding: 0; font-size: inherit; }

table { border-collapse: collapse; width: 100%; font-size: .93rem; }
.scroll { overflow-x: auto; margin-bottom: 1.4rem; }
th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { font-weight: 600; font-size: .82rem; text-transform: uppercase;
  letter-spacing: .04em; color: var(--muted); }
td code { white-space: nowrap; }

.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 1rem 1.15rem; margin-bottom: .7rem; }
.card h3 { margin: 0 0 .3rem; font-size: 1rem; }
.card h3 a { text-decoration: none; }
.card p { margin: 0; font-size: .93rem; color: var(--muted); }
.grid { display: grid; gap: .7rem; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); }

.tag { display: inline-block; font-size: .74rem; letter-spacing: .03em;
  background: var(--accent-soft); color: var(--accent); border-radius: 999px;
  padding: .12rem .55rem; margin-right: .3rem; white-space: nowrap; }
.note { background: var(--warn-bg); border: 1px solid var(--warn-line);
  border-radius: 8px; padding: .8rem 1rem; margin: 1.2rem 0; font-size: .93rem; }
.note strong { display: block; margin-bottom: .2rem; }

dl.facts { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1.2rem;
  margin: 0 0 1.6rem; font-size: .94rem; }
dl.facts dt { color: var(--muted); }
dl.facts dd { margin: 0; }

footer { border-top: 1px solid var(--line); margin-top: 4rem; padding-top: 1.4rem;
  color: var(--muted); font-size: .87rem; }
img, svg { max-width: 100%; }
"""


# ---------------------------------------------------------------- tiny helpers

def esc(text):
    return html.escape(str(text), quote=True)


def inline(text):
    """The only markup the catalog uses in its blurbs: **bold** and `code`."""
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    out = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def page(title, body, nav_here=None, depth=0):
    up = "../" * depth
    items = [("Start", "index.html", "index"),
             ("Catalog", "pieces/index.html", "pieces"),
             ("Profiles", "profiles.html", "profiles"),
             ("Commands", "commands.html", "commands")]
    links = "".join(
        f'<a href="{up}{href}"'
        + (' aria-current="page"' if key == nav_here else "")
        + f">{esc(label)}</a>"
        for label, href, key in items)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="color-scheme" content="light dark">
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="{up}index.html">W4VE docs</a>
<nav>{links}</nav>
</div></header>
<main class="wrap">
{body}
<footer>
Generated from <a href="https://github.com/CodeW4VE/registry">the catalog</a>.
If a page here is wrong, the fix belongs in <code>pieces.toml</code>, not in the page.
</footer>
</main>
</body>
</html>
"""


def mc_versions(piece):
    """Which Minecraft versions this piece actually ships for, from its
    releases. Deliberately not the `mc` range in the catalog: that one is a
    promise somebody typed, and it has been wrong."""
    found = set()
    for rel in piece.get("releases") or []:
        found.update(rel.get("minecraft") or ())
    return sorted(found, key=vkey)


def vkey(version):
    return tuple(int(n) for n in re.findall(r"\d+", version))


# Sources and javadoc jars ride along in a release and are not what anybody
# wants to download. The CLI skips them too.
JUNK = ("-sources.jar", "-dev.jar", "-javadoc.jar", "-sources-dev.jar")


def installable(files):
    """The files of a release, the ones people actually install first."""
    real = [f for f in files if not f["name"].lower().endswith(JUNK)]
    return sorted(real or files, key=lambda f: vkey(f["name"]))


# ------------------------------------------------------------------ the pages

def render_piece(piece, pieces):
    pid = piece["id"]
    title = piece["name"]
    body = [f"<h1>{esc(title)}</h1>"]
    body.append(f'<p class="lede">{inline(piece.get("blurb") or piece["summary"])}</p>')

    facts = []
    facts.append(("Kind", esc(TYPE_LABEL.get(piece.get("type"), piece.get("type", "?")))))
    if piece.get("side") in SIDE_LABEL:
        facts.append(("Where it goes", esc(SIDE_LABEL[piece["side"]])))
    versions = mc_versions(piece)
    if versions:
        facts.append(("Minecraft", ", ".join(esc(v) for v in versions)))
    elif piece.get("mc"):
        facts.append(("Minecraft", f'<code>{esc(piece["mc"])}</code>'))
    if piece.get("latest"):
        facts.append(("Latest", f'<code>{esc(piece["latest"])}</code>'))
    if piece.get("install_dir") and piece["install_dir"] != ".":
        facts.append(("Installs into", f'<code>{esc(piece["install_dir"])}/</code>'))
    if piece.get("requires"):
        facts.append(("Needs", ", ".join(
            f'<a href="{esc(r)}.html">{esc(pieces.get(r, {}).get("name", r))}</a>'
            if r in pieces else esc(r) for r in piece["requires"])))
    links = []
    if piece.get("repo"):
        links.append(f'<a href="https://github.com/{esc(piece["repo"])}">GitHub</a>')
    if piece.get("modrinth"):
        links.append(f'<a href="https://modrinth.com/mod/{esc(piece["modrinth"])}">Modrinth</a>')
    if piece.get("upstream"):
        links.append(f'fork of <a href="https://github.com/{esc(piece["upstream"])}">'
                     f'{esc(piece["upstream"])}</a>')
    if links:
        facts.append(("Links", " &middot; ".join(links)))
    body.append('<dl class="facts">' + "".join(
        f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts) + "</dl>")

    if piece.get("type") not in ("tool", "runtime", "discord-bot", "service"):
        body.append("<h2>Install it</h2>")
        body.append(f"<pre><code>w4ve install {esc(pid)}</code></pre>")

    conflicts = piece.get("conflicts") or []
    if conflicts:
        rows = []
        for c in conflicts:
            if isinstance(c, dict):
                other = c.get("with", "?")
                why = c.get("why", "")
                mine, theirs = c.get("mine", "any"), c.get("theirs", "any")
                rows.append(f"<tr><td><code>{esc(other)}</code></td>"
                            f"<td><code>{esc(mine)}</code> with <code>{esc(theirs)}</code></td>"
                            f"<td>{inline(why)}</td></tr>")
            else:
                rows.append(f"<tr><td><code>{esc(c)}</code></td><td>any</td><td></td></tr>")
        body.append("<h2>Does not get along with</h2>")
        body.append('<div class="scroll"><table><tr><th>Piece</th><th>Versions</th>'
                    "<th>Why</th></tr>" + "".join(rows) + "</table></div>")
        body.append("<p class=\"muted\">The CLI refuses an update that would put "
                    "one of these pairs together, and says which one.</p>")

    releases = piece.get("releases") or []
    if releases:
        body.append("<h2>Downloads</h2>")
        rows = []
        for rel in releases[:8]:
            mcs = ", ".join(esc(v) for v in
                            sorted(rel.get("minecraft") or [], key=vkey)) or "&mdash;"
            files = installable(rel.get("files") or [])
            first = files[0] if files else None
            link = (f'<a href="{esc(first["url"])}">{esc(first["name"])}</a>'
                    if first else "&mdash;")
            if len(files) > 1:
                link += f' <span class="muted">and {len(files) - 1} more</span>'
            rows.append(f'<tr><td><code>{esc(rel["version"])}</code></td>'
                        f"<td>{mcs}</td><td>{link}</td></tr>")
        body.append('<div class="scroll"><table><tr><th>Version</th>'
                    "<th>Minecraft</th><th>File</th></tr>"
                    + "".join(rows) + "</table></div>")
    else:
        body.append('<div class="note"><strong>Nothing to download yet</strong>'
                    "This piece is in the catalog so the plan is public, but it "
                    "has no release you can install.</div>")

    return page(f"{title} - W4VE docs", "\n".join(body), "pieces", depth=1)


def render_catalog(pieces):
    body = ["<h1>The catalog</h1>",
            '<p class="lede">Everything <code>w4ve install</code> knows how to '
            "put on a server, and everything it knows not to put next to each "
            "other.</p>"]
    by_type = {}
    for p in pieces.values():
        by_type.setdefault(p.get("type"), []).append(p)
    for kind in TYPE_ORDER:
        group = sorted(by_type.get(kind, []), key=lambda p: p["name"].lower())
        if not group:
            continue
        body.append(f"<h2>{esc(TYPE_LABEL.get(kind, kind))}</h2>")
        cards = []
        for p in group:
            versions = mc_versions(p)
            tag = ""
            if versions:
                tag = f'<span class="tag">MC {esc(versions[-1])}</span>'
            elif not p.get("releases"):
                tag = '<span class="tag">not released</span>'
            cards.append(
                f'<div class="card"><h3><a href="{esc(p["id"])}.html">'
                f'{esc(p["name"])}</a></h3>{tag}'
                f'<p>{inline(p["summary"])}</p></div>')
        body.append('<div class="grid">' + "".join(cards) + "</div>")
    return page("Catalog - W4VE docs", "\n".join(body), "pieces", depth=1)


def render_profiles(index):
    pieces = index["pieces"]
    body = ["<h1>Profiles</h1>",
            '<p class="lede">Curated sets, so you do not pick fifteen mods one '
            "by one. One command installs the whole thing.</p>"]
    for key, prof in index.get("profiles", {}).items():
        body.append(f'<h2>{esc(prof["name"])}</h2>')
        body.append(f'<p>{inline(prof["description"])}</p>')
        body.append(f"<pre><code>w4ve install --profile {esc(key)}</code></pre>")
        listed = []
        for pid in prof.get("pieces", []):
            name = pieces.get(pid, {}).get("name", pid)
            listed.append(f'<a href="pieces/{esc(pid)}.html">{esc(name)}</a>')
        body.append(f'<p class="muted">{len(listed)} pieces: '
                    + ", ".join(listed) + "</p>")
    return page("Profiles - W4VE docs", "\n".join(body), "profiles")


def render_commands(help_texts):
    body = ["<h1>Commands</h1>",
            '<p class="lede">Straight from <code>w4ve --help</code>, so this '
            "page cannot describe a flag the command does not have.</p>",
            '<div class="note"><strong>Every command takes <code>-n</code>'
            "</strong>It shows what would happen and writes nothing. When in "
            "doubt, run it with <code>-n</code> first.</div>"]
    if "" in help_texts:
        body.append("<h2>Overview</h2>")
        body.append(f"<pre><code>{esc(help_texts[''])}</code></pre>")
    for name in COMMANDS:
        if name not in help_texts:
            continue
        body.append(f'<h2 id="{esc(name)}">w4ve {esc(name)}</h2>')
        body.append(f"<pre><code>{esc(help_texts[name])}</code></pre>")
    return page("Commands - W4VE docs", "\n".join(body), "commands")


def render_home(index):
    reg = index["registry"]
    pieces = index["pieces"]
    counts = {}
    for p in pieces.values():
        counts[p.get("type")] = counts.get(p.get("type"), 0) + 1
    mods = counts.get("fabric-mod", 0)
    plugins = counts.get("mcdr-plugin", 0)
    targets = ", ".join(reg.get("mc_targets", []))

    body = [
        f"<h1>{esc(reg['name'])}</h1>",
        f'<p class="lede">{esc(reg["description"])}</p>',
        "<h2>Install the command</h2>",
        "<p>One file, standard library only, Python 3.8 or newer. No pip, no "
        "virtualenv, nothing to install first.</p>",
        "<pre><code>curl -LO https://github.com/CodeW4VE/w4ve/releases/latest/download/w4ve.py\n"
        "chmod +x w4ve.py &amp;&amp; sudo mv w4ve.py /usr/local/bin/w4ve</code></pre>",
        "<h2>Point it at a server</h2>",
        "<pre><code>cd /path/to/your/server\n"
        "w4ve init                  # writes w4ve.toml\n"
        "w4ve adopt                 # writes down the mods this server already has\n"
        "w4ve install shapeboard    # downloads it, puts it where it goes\n"
        "w4ve status                # what is installed, what needs a restart\n"
        "w4ve doctor                # what is wrong, before the server finds out</code></pre>",
        '<div class="note"><strong>It reads what is already there</strong>'
        "<code>w4ve adopt</code> opens every jar and reads the manifest inside "
        "instead of guessing from the file name, so a server you have been "
        "running for a year is understood as it is, and the mods it does not "
        "recognise are left alone.</div>",
        "<h2>What is in the catalog</h2>",
        f"<p>{len(pieces)} pieces: {mods} Fabric mods, {plugins} MCDReforged "
        f"plugins, and the tools and bots around them. Kept honest for "
        f"Minecraft {esc(targets)}, because those are the versions our own "
        f"servers run.</p>",
        '<div class="grid">'
        '<div class="card"><h3><a href="pieces/index.html">Browse the catalog</a></h3>'
        "<p>Every piece, what it needs, and what it refuses to sit next to.</p></div>"
        '<div class="card"><h3><a href="profiles.html">Profiles</a></h3>'
        "<p>A whole technical server in one command.</p></div>"
        '<div class="card"><h3><a href="commands.html">Commands</a></h3>'
        "<p>The reference, generated from the CLI itself.</p></div>"
        "</div>",
        "<h2>Why this exists</h2>",
        "<p>These tools grew one at a time out of running a technical server, "
        "and for a while the only way to install them was to know which jar "
        "went where. The catalog is that knowledge written down in one place, "
        "and the command is what reads it.</p>",
    ]
    return page("W4VE docs", "\n".join(body), "index")


# ---------------------------------------------------------------------- driver

def cli_help(cli_path):
    """Ask the CLI for its own help, one call per command."""
    texts = {}
    for name in [""] + COMMANDS:
        cmd = [sys.executable, str(cli_path)] + ([name] if name else []) + ["--help"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                 env={**os.environ, "COLUMNS": "84"})
        except (OSError, subprocess.SubprocessError) as err:
            print(f"  ! {name or 'w4ve'} --help failed: {err}", file=sys.stderr)
            continue
        if out.returncode == 0 and out.stdout.strip():
            texts[name] = out.stdout.rstrip()
    return texts


def fetch_cli(dest):
    print(f"fetching the CLI from {CLI_RELEASE}")
    req = urllib.request.Request(CLI_RELEASE, headers={"User-Agent": "w4ve-docs"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", help="path to w4ve.py (default: the latest release)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--serve", action="store_true",
                    help="serve the result on http://localhost:8080")
    args = ap.parse_args()

    index = json.loads(INDEX.read_text())
    pieces = index["pieces"]
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "pieces").mkdir(parents=True)

    cli = Path(args.cli) if args.cli else None
    if cli is None:
        try:
            cli = fetch_cli(out / ".w4ve.py")
        except Exception as err:                       # noqa: BLE001
            print(f"  ! could not fetch the CLI: {err}", file=sys.stderr)
    helps = cli_help(cli) if cli and Path(cli).exists() else {}
    if not helps:
        print("  ! no command reference: the CLI could not be run", file=sys.stderr)

    (out / "index.html").write_text(render_home(index))
    (out / "profiles.html").write_text(render_profiles(index))
    if helps:
        (out / "commands.html").write_text(render_commands(helps))
    (out / "pieces" / "index.html").write_text(render_catalog(pieces))
    for piece in pieces.values():
        (out / "pieces" / f"{piece['id']}.html").write_text(
            render_piece(piece, pieces))

    scratch = out / ".w4ve.py"
    if scratch.exists():
        scratch.unlink()

    written = sum(1 for _ in out.rglob("*.html"))
    print(f"wrote {written} pages into {out}")

    if args.serve:
        import http.server
        import functools
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(out))
        print("serving on http://localhost:8080, ctrl-c to stop")
        http.server.HTTPServer(("127.0.0.1", 8080), handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
