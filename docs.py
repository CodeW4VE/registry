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

# The look is a printed technical manual, not a landing page, because that is
# what this is: dense reference you come to with a question. Everything here is
# a decision away from the defaults an editor hands you, and each one has a
# reason:
#
#   serif for prose, mono for anything a machine said   not one neutral sans
#   paper and ink, redstone red for accent              not the safe teal
#   rules and margins                                   not cards and shadows
#   square corners                                      not pills
#
# The accent comes from the subject matter (redstone) instead of from a
# framework's default palette. No web fonts: nothing here loads from anywhere.
CSS = """
:root {
  --paper: #f4f1ea; --ink: #191712; --faded: #6a6357; --rule: #ccc4b4;
  --accent: #8c2f1f; --accent-bright: #b03f28;
  --quote: #ece7db; --flag: #f0e5c8;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #12100d; --ink: #e4ddcf; --faded: #968d7c; --rule: #362f26;
    --accent: #d4674a; --accent-bright: #e8825f;
    --quote: #1b1814; --flag: #241d12;
  }
}
:root[data-theme="dark"] {
  --paper: #12100d; --ink: #e4ddcf; --faded: #968d7c; --rule: #362f26;
  --accent: #d4674a; --accent-bright: #e8825f;
  --quote: #1b1814; --flag: #241d12;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font: 17px/1.6 "Iowan Old Style", "Palatino Linotype", Palatino, Charter,
        "Bitstream Charter", "Source Serif 4", Georgia, serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 0 1.4rem 6rem; }

code, pre, .mono, th, .tag, header.top, .facts dt {
  font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono",
               ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* The masthead of a manual: a double rule, and the section you are in. */
header.top { border-bottom: 3px double var(--rule); margin-bottom: 3rem; }
header.top .wrap { padding-top: .9rem; padding-bottom: .8rem;
  display: flex; gap: 1.6rem; align-items: baseline; flex-wrap: wrap;
  font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; }
header.top a.brand { font-weight: 700; color: var(--ink); text-decoration: none; }
header.top nav { display: flex; gap: 1.4rem; flex-wrap: wrap; }
header.top nav a { color: var(--faded); text-decoration: none; }
header.top nav a:hover { color: var(--accent); }
header.top nav a[aria-current] { color: var(--ink);
  box-shadow: inset 0 -2px 0 var(--accent); }

h1 { font-size: 2.1rem; line-height: 1.15; margin: 0 0 .5rem; font-weight: 400; }
h2 { font-size: 1.05rem; margin: 3rem 0 .9rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .09em;
  padding-bottom: .35rem; border-bottom: 1px solid var(--rule); }
h3 { font-size: 1.05rem; margin: 2rem 0 .4rem; font-weight: 700; }
p { margin: 0 0 1.05rem; }
a { color: var(--accent); text-underline-offset: .16em;
  text-decoration-thickness: 1px; }
a:hover { color: var(--accent-bright); }
.lede { font-size: 1.2rem; line-height: 1.5; margin-bottom: 2.2rem;
  color: var(--faded); font-style: italic; }
.muted { color: var(--faded); }

code { font-size: .82em; }
pre { background: var(--quote); border-left: 3px solid var(--rule);
  padding: .9rem 1.1rem; overflow-x: auto; font-size: .8rem; line-height: 1.6; }
pre code { font-size: inherit; }

table { border-collapse: collapse; width: 100%; font-size: .92rem; }
.scroll { overflow-x: auto; margin-bottom: 1.6rem; }
th, td { text-align: left; padding: .45rem .8rem .45rem 0; vertical-align: top;
  border-bottom: 1px solid var(--rule); }
th { font-size: .7rem; text-transform: uppercase; letter-spacing: .1em;
  color: var(--faded); font-weight: 400; border-bottom-width: 2px; }
td code { white-space: nowrap; }

/* The catalog is an index, so it is set like one: name in the margin, what it
   is beside it. No cards, no grid of three. */
dl.index { margin: 0 0 1rem; }
dl.index dt { margin-top: 1.1rem; font-weight: 700; font-size: 1rem; }
dl.index dt a { text-decoration: none; }
dl.index dt a:hover { text-decoration: underline; }
dl.index dd { margin: .1rem 0 0; color: var(--faded); font-size: .95rem; }
@media (min-width: 46rem) {
  dl.index dt { float: left; clear: left; width: 13rem; margin-top: .55rem;
    padding-right: 1rem; }
  dl.index dd { margin-left: 13rem; margin-top: .55rem; min-height: 1.6rem; }
}

.tag { font-size: .68rem; letter-spacing: .08em; color: var(--accent);
  text-transform: uppercase; white-space: nowrap; }
.tag::before { content: "["; } .tag::after { content: "]"; }

.note { background: var(--flag); border-left: 3px solid var(--accent);
  padding: .85rem 1.1rem; margin: 1.5rem 0; font-size: .95rem; }
.note strong { display: block; text-transform: uppercase; font-size: .72rem;
  letter-spacing: .1em; margin-bottom: .35rem; }

dl.facts { display: grid; grid-template-columns: max-content 1fr;
  gap: .3rem 1.4rem; margin: 0 0 2rem; font-size: .95rem;
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule);
  padding: .9rem 0; }
dl.facts dt { color: var(--faded); font-size: .72rem; text-transform: uppercase;
  letter-spacing: .08em; padding-top: .22rem; }
dl.facts dd { margin: 0; }

footer { border-top: 3px double var(--rule); margin-top: 5rem; padding-top: 1.3rem;
  color: var(--faded); font-size: .85rem; }
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
        rows = []
        for p in group:
            versions = mc_versions(p)
            tag = ""
            if versions:
                tag = f' <span class="tag">up to MC {esc(versions[-1])}</span>'
            elif not p.get("releases"):
                tag = ' <span class="tag">not released</span>'
            rows.append(
                f'<dt><a href="{esc(p["id"])}.html">{esc(p["name"])}</a></dt>'
                f'<dd>{inline(p["summary"])}{tag}</dd>')
        body.append('<dl class="index">' + "".join(rows) + "</dl>")
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
        '<dl class="index">'
        '<dt><a href="pieces/index.html">The catalog</a></dt>'
        "<dd>Every piece, what it needs, and what it refuses to sit next to.</dd>"
        '<dt><a href="profiles.html">Profiles</a></dt>'
        "<dd>A whole technical server in one command.</dd>"
        '<dt><a href="commands.html">Commands</a></dt>'
        "<dd>The reference, generated from the CLI itself.</dd>"
        "</dl>",
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
