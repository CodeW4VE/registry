#!/usr/bin/env python3
"""Build docs.w4ve.xyz out of index.json and the CLI itself.

    python3 docs.py                 write the site into site/
    python3 docs.py --cli PATH      use that w4ve.py for the command reference
    python3 docs.py --serve         build, then serve it on http://localhost:8080

Nothing here is written by hand twice. The page of a piece comes from the
catalog, and the command reference comes from asking the CLI for its own help,
so neither can drift from what is really published. If a page says something
wrong, the fix belongs in pieces.toml or in the CLI's own help text.

The site is bilingual: English at the root, Spanish under /es/. The English
copy lives in this file, the Spanish in i18n/es.toml, and anything missing
from the translation falls back to English instead of breaking.

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
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.json"
ASSETS = HERE / "assets"
I18N = HERE / "i18n"
OUT = HERE / "site"

CLI_RELEASE = "https://github.com/CodeW4VE/w4ve/releases/latest/download/w4ve.py"
# Only a fallback. The real list is asked of the CLI (see discover_commands):
# this was a hand written list, and it quietly went stale the day the runtime
# arrived. Thirteen commands existed, worked, and were documented nowhere,
# because nothing here was reading anything to find out.
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

# Colour is spent on the two questions you actually ask while reading a catalog
# of seventy things: is this yours, and can I install it today. Gold for our
# own code, blue for a fork we maintain, nothing at all for somebody else's.
ORIGIN_LABEL = {"w4ve": "Ours", "fork": "Our fork", "external": "External"}
ORIGIN_CLASS = {"w4ve": "ours", "fork": "fork"}
STATUS_LABEL = {"stable": "Stable", "beta": "Beta", "planned": "Planned",
                "unreleased": "Unreleased", "infra": "Infrastructure"}
# Stable is the normal case and gets no badge: a badge on everything is a
# badge on nothing.
STATUS_CLASS = {"beta": "beta", "planned": "planned",
                "unreleased": "planned", "infra": "infra"}


# --------------------------------------------------------------------- styling

# The stylesheet is a hand-written file in assets/, not a string in here: it is
# design, it is long, and it is the one thing in this repo that is not derived
# from the catalog. docs.py copies it, and the fonts beside it, into the site.
#
# Shipping it as a file instead of inlining it also fixes the boring problem
# that the font URLs would otherwise have to know how deep the page is.


# ------------------------------------------------------------------- languages

class Lang:
    """One language of the site. The code is also the URL prefix, except for
    English, which lives at the root."""

    def __init__(self, code, data, label):
        self.code = code
        self.data = data
        self.label = label

    @property
    def prefix(self):
        return "" if self.code == "en" else f"{self.code}/"

    def t(self, section, key, default):
        """Translated string, or the English one. A missing key is not an
        error: a piece added today shows up untranslated tomorrow."""
        return self.data.get(section, {}).get(key, default)

    def piece(self, pid, field, default):
        return self.data.get("pieces", {}).get(pid, {}).get(field) or default


LANG_NAMES = {"es": "Español"}


def load_langs():
    langs = [Lang("en", {}, "English")]
    for path in sorted(I18N.glob("*.toml")) if I18N.exists() else []:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        langs.append(Lang(path.stem, data, LANG_NAMES.get(path.stem, path.stem)))
    return langs


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


def callout(kind, title, body):
    """info, warn or danger. Three of them exist because three things are worth
    interrupting a paragraph for; there is no fourth colour for decoration."""
    return (f'<div class="callout callout--{kind}">'
            f'<p class="callout-title">{title}</p><p>{body}</p></div>')


def type_label(lang, kind):
    return lang.t("ui", f"type_{kind}", TYPE_LABEL.get(kind, kind))


def side_label(lang, side):
    if side not in SIDE_LABEL:
        return None
    return lang.t("ui", f"side_{side}", SIDE_LABEL[side])


def badges(lang, piece):
    """Origin and status, the two small coloured marks a piece can carry."""
    out = []
    origin = piece.get("origin")
    if origin in ORIGIN_CLASS:
        label = lang.t("ui", f"origin_{origin}", ORIGIN_LABEL[origin])
        out.append(f'<span class="badge badge--{ORIGIN_CLASS[origin]}">'
                   f"{esc(label)}</span>")
    status = piece.get("status")
    if status in STATUS_CLASS:
        label = lang.t("ui", f"status_{status}", STATUS_LABEL[status])
        out.append(f'<span class="badge badge--{STATUS_CLASS[status]}">'
                   f"{esc(label)}</span>")
    return "".join(out)


# ------------------------------------------------------------------- the shell

# (key, path inside the language root, translation key, English label)
SECTIONS = [("index", "index.html", "start", "Start"),
            ("pieces", "pieces/index.html", "the_catalog", "The catalog"),
            ("profiles", "profiles.html", "profiles", "Profiles"),
            ("commands", "commands.html", "commands", "Commands")]

# [(kind, [(id, name, origin), ...])] for the sidebar, filled by build_nav().
NAV_GROUPS = []


def build_nav(pieces):
    """The catalog as the sidebar shows it: grouped by kind, in the same order
    as the catalog page, so the two never disagree."""
    NAV_GROUPS.clear()
    by_type = {}
    for p in pieces.values():
        by_type.setdefault(p.get("type"), []).append(p)
    for kind in TYPE_ORDER:
        group = sorted(by_type.get(kind, []), key=lambda p: p["name"].lower())
        if group:
            NAV_GROUPS.append(
                (kind, [(p["id"], p["name"], p.get("origin")) for p in group]))


def sidebar(lang, up, nav_here, active_piece):
    def href(path):
        return f"{up}{lang.prefix}{path}"

    out = [f'<a class="brand" href="{href("index.html")}">'
           '<span class="brand-mark">W4VE</span>'
           f'<span class="brand-sub">{esc(lang.t("ui", "docs", "docs"))}</span></a>',
           "<nav>",
           f'<p class="navlabel">{esc(lang.t("ui", "guide", "Guide"))}</p>',
           '<div class="navsections">']
    for key, path, ui_key, label in SECTIONS:
        here = ' aria-current="page"' if key == nav_here and not active_piece else ""
        out.append(f'<a href="{href(path)}"{here}>'
                   f'{esc(lang.t("ui", ui_key, label))}</a>')
    out.append("</div>")

    out.append('<p class="navlabel">'
               f'{esc(lang.t("ui", "catalog_label", "Catalog"))}</p>')
    for kind, entries in NAV_GROUPS:
        open_ = " open" if any(pid == active_piece for pid, _, _ in entries) else ""
        links = []
        for pid, name, origin in entries:
            current = ' aria-current="page"' if pid == active_piece else ""
            # One gold dot, on our own code. In a list where most rows are
            # other people's mods, that is the thing a visitor is looking for.
            dot = ('<span class="dot" aria-hidden="true"></span>'
                   if origin in ("w4ve", "fork") else "")
            links.append(f'<a href="{href("pieces/" + pid + ".html")}"{current}>'
                         f"{dot}{esc(name)}</a>")
        out.append(f'<details class="navgroup"{open_}>'
                   f"<summary>{esc(type_label(lang, kind))}"
                   f'<span class="count">{len(entries)}</span></summary>'
                   f'<div class="navlist">{"".join(links)}</div></details>')
    out.append("</nav>")
    return "\n".join(out)


def lang_switch(lang, langs, up, path):
    """The same page in the other language, never the home page: dumping you
    back at the start is the classic way a language switcher annoys people."""
    if len(langs) < 2:
        return ""
    items = []
    for other in langs:
        here = ' aria-current="true"' if other.code == lang.code else ""
        items.append(f'<a href="{up}{other.prefix}{path}"{here} '
                     f'lang="{other.code}">{esc(other.label)}</a>')
    label = lang.t("ui", "language", "Language")
    return (f'<div class="langs"><span class="langs-label">{esc(label)}</span>'
            f'{"".join(items)}</div>')


HEADING = re.compile(r"<h2(?P<attrs>[^>]*)>(?P<text>.*?)</h2>", re.S)


def headings(body):
    """Give every h2 an id and hand back the list, so the page can carry its
    own table of contents without anybody writing one."""
    found, seen = [], set()

    def fix(match):
        attrs, text = match.group("attrs"), match.group("text")
        plain = re.sub(r"<[^>]+>", "", text).strip()
        given = re.search(r'id="([^"]+)"', attrs)
        if given:
            hid = given.group(1)
        else:
            hid = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "section"
            n, base = 2, hid
            while hid in seen:
                hid, n = f"{base}-{n}", n + 1
            attrs = f' id="{esc(hid)}"' + attrs
        seen.add(hid)
        found.append((hid, plain))
        return f"<h2{attrs}>{text}</h2>"

    return HEADING.sub(fix, body), found


def page(lang, langs, path, title, body, nav_here=None, active_piece=None):
    depth = path.count("/") + (0 if lang.code == "en" else 1)
    up = "../" * depth
    body, heads = headings(body)
    on_this = lang.t("ui", "on_this_page", "On this page")
    toc = ""
    if len(heads) > 1:
        toc = (f'<nav class="toc" aria-label="{esc(on_this)}">'
               f"<p>{esc(on_this)}</p>"
               + "".join(f'<a href="#{esc(hid)}">{text}</a>' for hid, text in heads)
               + "</nav>")
    foot = lang.t("ui", "foot",
                  'Generated from <a href="https://github.com/CodeW4VE/registry">'
                  "the catalog</a>. If a page here is wrong, the fix belongs in "
                  "<code>pieces.toml</code>, not in the page.")
    return f"""<!doctype html>
<html lang="{lang.code}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="color-scheme" content="dark">
<link rel="stylesheet" href="{up}assets/docs.css">
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#content">{esc(lang.t("ui", "skip", "Skip to content"))}</a>
<div class="shell">
<aside class="sidebar">
{sidebar(lang, up, nav_here, active_piece)}
{lang_switch(lang, langs, up, path)}
</aside>
<main class="main" id="content">
<article class="prose">
{body}
</article>
<footer class="foot">
{foot}
</footer>
</main>
{toc}
</div>
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


def mc_range(lang, versions):
    """Thirteen version numbers in a row is a wall, not an answer. Past three,
    say the span and how many there are; the download table has the exact list
    per release anyway."""
    if not versions:
        return "&mdash;"
    if len(versions) <= 3:
        return ", ".join(esc(v) for v in versions)
    return (f"{esc(versions[0])} {esc(lang.t('ui', 'to', 'to'))} "
            f"{esc(versions[-1])} "
            f'<span class="muted">({len(versions)} '
            f"{esc(lang.t('ui', 'versions', 'versions'))})</span>")


# Sources and javadoc jars ride along in a release and are not what anybody
# wants to download. The CLI skips them too.
JUNK = ("-sources.jar", "-dev.jar", "-javadoc.jar", "-sources-dev.jar")


def installable(files):
    """The files of a release, the ones people actually install first."""
    real = [f for f in files if not f["name"].lower().endswith(JUNK)]
    return sorted(real or files, key=lambda f: vkey(f["name"]))


# ------------------------------------------------------------------ the pages

def render_piece(lang, langs, piece, pieces):
    pid = piece["id"]
    title = piece["name"]
    kind = type_label(lang, piece.get("type"))
    body = [f'<p class="eyebrow"><a href="index.html">'
            f'{esc(lang.t("ui", "catalog_label", "Catalog"))}</a> / {esc(kind)}</p>',
            f"<h1>{esc(title)}</h1>"]
    marks = badges(lang, piece)
    if marks:
        body.append(f'<p class="badgerow">{marks}</p>')
    summary = lang.piece(pid, "summary", piece["summary"])
    long_ = lang.piece(pid, "blurb", None)
    if long_ is None and lang.code == "en":
        long_ = piece.get("blurb")
    body.append(f'<p class="lede">{inline(long_ or summary)}</p>')

    facts = []
    facts.append((lang.t("ui", "kind", "Kind"), esc(kind)))
    side = side_label(lang, piece.get("side"))
    if side:
        facts.append((lang.t("ui", "where", "Where it goes"), esc(side)))
    versions = mc_versions(piece)
    if versions:
        facts.append((lang.t("ui", "minecraft", "Minecraft"),
                      mc_range(lang, versions)))
    elif piece.get("mc"):
        facts.append((lang.t("ui", "minecraft", "Minecraft"),
                      f'<code>{esc(piece["mc"])}</code>'))
    if piece.get("latest"):
        facts.append((lang.t("ui", "latest", "Latest"),
                      f'<code>{esc(piece["latest"])}</code>'))
    if piece.get("install_dir") and piece["install_dir"] != ".":
        facts.append((lang.t("ui", "installs_into", "Installs into"),
                      f'<code>{esc(piece["install_dir"])}/</code>'))
    if piece.get("requires"):
        facts.append((lang.t("ui", "needs", "Needs"), ", ".join(
            f'<a href="{esc(r)}.html">{esc(pieces.get(r, {}).get("name", r))}</a>'
            if r in pieces else esc(r) for r in piece["requires"])))
    links = []
    if piece.get("repo"):
        links.append(f'<a href="https://github.com/{esc(piece["repo"])}">GitHub</a>')
    if piece.get("modrinth"):
        links.append(f'<a href="https://modrinth.com/mod/{esc(piece["modrinth"])}">Modrinth</a>')
    if piece.get("upstream"):
        links.append(f'{esc(lang.t("ui", "fork_of", "fork of"))} '
                     f'<a href="https://github.com/{esc(piece["upstream"])}">'
                     f'{esc(piece["upstream"])}</a>')
    if links:
        facts.append((lang.t("ui", "links", "Links"), " &middot; ".join(links)))
    body.append('<dl class="facts">' + "".join(
        f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in facts) + "</dl>")

    if piece.get("type") not in ("tool", "runtime", "discord-bot", "service"):
        body.append(f'<h2>{esc(lang.t("ui", "install_it", "Install it"))}</h2>')
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
                            f"<td><code>{esc(mine)}</code> / "
                            f"<code>{esc(theirs)}</code></td>"
                            f"<td>{inline(why)}</td></tr>")
            else:
                rows.append(f"<tr><td><code>{esc(c)}</code></td>"
                            "<td>any</td><td></td></tr>")
        body.append(f'<h2>{esc(lang.t("ui", "conflicts_title", "Does not get along with"))}</h2>')
        body.append('<div class="scroll"><table><thead><tr>'
                    f'<th>{esc(lang.t("ui", "conflicts_piece", "Piece"))}</th>'
                    f'<th>{esc(lang.t("ui", "conflicts_versions", "Versions"))}</th>'
                    f'<th>{esc(lang.t("ui", "conflicts_why", "Why"))}</th>'
                    "</tr></thead><tbody>" + "".join(rows)
                    + "</tbody></table></div>")
        body.append('<p class="muted">' + esc(lang.t(
            "ui", "conflicts_note",
            "The CLI refuses an update that would put one of these pairs "
            "together, and says which one.")) + "</p>")

    releases = piece.get("releases") or []
    if releases:
        body.append(f'<h2>{esc(lang.t("ui", "downloads", "Downloads"))}</h2>')
        rows = []
        for rel in releases[:8]:
            mcs = mc_range(lang, sorted(rel.get("minecraft") or [], key=vkey))
            files = installable(rel.get("files") or [])
            first = files[0] if files else None
            link = (f'<a href="{esc(first["url"])}">{esc(first["name"])}</a>'
                    if first else "&mdash;")
            if len(files) > 1:
                more = lang.t("ui", "and_more", "and {n} more")
                link += (f' <span class="muted">'
                         f"{esc(more.format(n=len(files) - 1))}</span>")
            rows.append(f'<tr><td><code>{esc(rel["version"])}</code></td>'
                        f"<td>{mcs}</td><td>{link}</td></tr>")
        body.append('<div class="scroll"><table><thead><tr>'
                    f'<th>{esc(lang.t("ui", "version", "Version"))}</th>'
                    f'<th>{esc(lang.t("ui", "minecraft", "Minecraft"))}</th>'
                    f'<th>{esc(lang.t("ui", "file", "File"))}</th>'
                    "</tr></thead><tbody>" + "".join(rows)
                    + "</tbody></table></div>")
    else:
        body.append(callout(
            "info",
            esc(lang.t("ui", "nothing_title", "Nothing to download yet")),
            esc(lang.t("ui", "nothing_body",
                       "This piece is in the catalog so the plan is public, but "
                       "it has no release you can install."))))

    return page(lang, langs, f"pieces/{pid}.html", f"{title} - W4VE docs",
                "\n".join(body), "pieces", active_piece=pid)


def render_catalog(lang, langs, pieces):
    body = [f'<h1>{esc(lang.t("catalog", "title", "The catalog"))}</h1>',
            '<p class="lede">' + lang.t(
                "catalog", "lede",
                "Everything <code>w4ve install</code> knows how to put on a "
                "server, and everything it knows not to put next to each "
                "other.") + "</p>"]
    by_type = {}
    for p in pieces.values():
        by_type.setdefault(p.get("type"), []).append(p)
    for kind in TYPE_ORDER:
        group = sorted(by_type.get(kind, []), key=lambda p: p["name"].lower())
        if not group:
            continue
        body.append(f"<h2>{esc(type_label(lang, kind))}</h2>")
        rows = []
        for p in group:
            versions = mc_versions(p)
            tag = ""
            if versions:
                tag = (f'<span class="tag">'
                       f'{esc(lang.t("ui", "up_to", "up to MC"))} '
                       f"{esc(versions[-1])}</span>")
            elif not p.get("releases"):
                tag = (f'<span class="tag">'
                       f'{esc(lang.t("ui", "not_released", "not released"))}</span>')
            rows.append(
                f'<a class="row" href="{esc(p["id"])}.html">'
                f'<span class="row-head"><span class="row-name">{esc(p["name"])}'
                f"</span>{badges(lang, p)}{tag}</span>"
                f'<span class="row-desc">'
                f'{inline(lang.piece(p["id"], "summary", p["summary"]))}</span></a>')
        body.append('<div class="rows">' + "".join(rows) + "</div>")
    return page(lang, langs, "pieces/index.html", "Catalog - W4VE docs",
                "\n".join(body), "pieces")


def render_profiles(lang, langs, index):
    pieces = index["pieces"]
    body = [f'<h1>{esc(lang.t("profiles", "title", "Profiles"))}</h1>',
            '<p class="lede">' + lang.t(
                "profiles", "lede",
                "Curated sets, so you do not pick fifteen mods one by one. One "
                "command installs the whole thing.") + "</p>"]
    for key, prof in index.get("profiles", {}).items():
        local = lang.data.get("profiles", {}).get(key, {})
        body.append(f'<h2>{esc(local.get("name") or prof["name"])}</h2>')
        body.append(f'<p>{inline(local.get("description") or prof["description"])}</p>')
        body.append(f"<pre><code>w4ve install --profile {esc(key)}</code></pre>")
        listed = []
        for pid in prof.get("pieces", []):
            name = pieces.get(pid, {}).get("name", pid)
            listed.append(f'<a href="pieces/{esc(pid)}.html">{esc(name)}</a>')
        # Twenty-five links in accent colour would be a stain, so the list of
        # members reads as a list and only turns gold under the cursor.
        body.append(f'<p class="eyebrow">{len(listed)} '
                    f'{esc(lang.t("ui", "pieces_word", "pieces"))}</p>')
        body.append('<ul class="linklist"><li>'
                    + "</li><li>".join(listed) + "</li></ul>")
    return page(lang, langs, "profiles.html", "Profiles - W4VE docs",
                "\n".join(body), "profiles")


def render_commands(lang, langs, help_texts, commands):
    body = [f'<h1>{esc(lang.t("commands", "title", "Commands"))}</h1>',
            '<p class="lede">' + lang.t(
                "commands", "lede",
                "Straight from <code>w4ve --help</code>, so this page cannot "
                "describe a flag the command does not have.") + "</p>",
            callout("info",
                    lang.t("commands", "note_title",
                           "Every command takes <code>-n</code>"),
                    lang.t("commands", "note_body",
                           "It shows what would happen and writes nothing. When "
                           "in doubt, run it with <code>-n</code> first."))]
    # The help below is the program's own output, copied verbatim. Translating
    # it here would mean this page could disagree with the terminal.
    if lang.code != "en":
        body.append(callout("warn",
                            lang.t("commands", "english_title",
                                   "The help output is in English"),
                            lang.t("commands", "english_body", "")))
    if "" in help_texts:
        body.append(f'<h2>{esc(lang.t("commands", "overview", "Overview"))}</h2>')
        body.append(f"<pre><code>{esc(help_texts[''])}</code></pre>")
    for name in commands:
        if name not in help_texts:
            continue
        body.append(f'<h2 id="{esc(name)}">w4ve {esc(name)}</h2>')
        body.append(f"<pre><code>{esc(help_texts[name])}</code></pre>")
    return page(lang, langs, "commands.html", "Commands - W4VE docs",
                "\n".join(body), "commands")


def render_home(lang, langs, index):
    reg = index["registry"]
    pieces = index["pieces"]
    counts = {}
    for p in pieces.values():
        counts[p.get("type")] = counts.get(p.get("type"), 0) + 1
    mods = counts.get("fabric-mod", 0)
    plugins = counts.get("mcdr-plugin", 0)
    ours = sum(1 for p in pieces.values() if p.get("origin") in ("w4ve", "fork"))
    targets = ", ".join(reg.get("mc_targets", []))

    def T(key, default):
        return lang.t("home", key, default)

    # Four numbers instead of a paragraph of adjectives: they answer "how big
    # is this" in the time it takes to look at them.
    stats = [(len(pieces), T("stat_pieces", "pieces in the catalog")),
             (mods, T("stat_mods", "Fabric mods")),
             (plugins, T("stat_plugins", "MCDR plugins")),
             (ours, T("stat_ours", "written by us"))]

    body = [
        '<div class="hero">',
        f'<p class="eyebrow">{esc(T("eyebrow", "W4VE / documentation"))}</p>',
        f"<h1>{esc(reg['name'])}</h1>",
        '<p class="hero-tagline">'
        f'{esc(lang.t("registry", "description", reg["description"]))}</p>',
        '<p class="cta">'
        f'<a class="btn" href="#install">{esc(T("cta_start", "Get started"))}</a>'
        '<a class="btn btn--ghost" href="pieces/index.html">'
        f'{esc(T("cta_catalog", "Browse the catalog"))}</a></p>',
        '<dl class="stats">' + "".join(
            f"<div><dt>{n}</dt><dd>{esc(label)}</dd></div>"
            for n, label in stats) + "</dl>",
        "</div>",

        f'<h2 id="install">{esc(T("install_title", "Install the command"))}</h2>',
        "<p>" + esc(T("install_body",
                      "One file, standard library only, Python 3.8 or newer. No "
                      "pip, no virtualenv, nothing to install first.")) + "</p>",
        "<pre><code>curl -LO https://github.com/CodeW4VE/w4ve/releases/latest/download/w4ve.py\n"
        "chmod +x w4ve.py &amp;&amp; sudo mv w4ve.py /usr/local/bin/w4ve</code></pre>",

        f'<h2>{esc(T("point_title", "Point it at a server"))}</h2>',
        "<pre><code>cd /path/to/your/server\n"
        f'w4ve init                  <span class="c"># '
        f'{esc(T("c_init", "writes w4ve.toml"))}</span>\n'
        f'w4ve adopt                 <span class="c"># '
        f'{esc(T("c_adopt", "writes down the mods this server already has"))}</span>\n'
        f'w4ve install shapeboard    <span class="c"># '
        f'{esc(T("c_install", "downloads it, puts it where it goes"))}</span>\n'
        f'w4ve status                <span class="c"># '
        f'{esc(T("c_status", "what is installed, what needs a restart"))}</span>\n'
        f'w4ve doctor                <span class="c"># '
        f'{esc(T("c_doctor", "what is wrong, before the server finds out"))}</span>'
        "</code></pre>",
        callout("info", T("adopt_title", "It reads what is already there"),
                T("adopt_body",
                  "<code>w4ve adopt</code> opens every jar and reads the "
                  "manifest inside instead of guessing from the file name, so a "
                  "server you have been running for a year is understood as it "
                  "is, and the mods it does not recognise are left alone.")),

        f'<h2>{esc(T("catalog_title", "What is in the catalog"))}</h2>',
        "<p>" + esc(T("catalog_body",
                      "{n} pieces: {mods} Fabric mods, {plugins} MCDReforged "
                      "plugins, and the tools and bots around them. Kept honest "
                      "for Minecraft {targets}, because those are the versions "
                      "our own servers run.").format(
                          n=len(pieces), mods=mods, plugins=plugins,
                          targets=targets)) + "</p>",
        '<div class="cards">'
        '<a class="card" href="pieces/index.html">'
        f'<span class="card-title">'
        f'{esc(lang.t("ui", "the_catalog", "The catalog"))}</span>'
        f'<span class="card-body">{esc(T("nav_catalog", "Every piece, what it needs, and what it refuses to sit next to."))}</span></a>'
        '<a class="card" href="profiles.html">'
        f'<span class="card-title">{esc(lang.t("ui", "profiles", "Profiles"))}</span>'
        f'<span class="card-body">{esc(T("nav_profiles", "A whole technical server in one command."))}</span></a>'
        '<a class="card" href="commands.html">'
        f'<span class="card-title">{esc(lang.t("ui", "commands", "Commands"))}</span>'
        f'<span class="card-body">{esc(T("nav_commands", "The reference, generated from the CLI itself."))}</span></a>'
        "</div>",

        f'<h2>{esc(T("why_title", "Why this exists"))}</h2>',
        "<p>" + esc(T("why_body",
                      "These tools grew one at a time out of running a technical "
                      "server, and for a while the only way to install them was "
                      "to know which jar went where. The catalog is that "
                      "knowledge written down in one place, and the command is "
                      "what reads it.")) + "</p>",
    ]
    return page(lang, langs, "index.html", "W4VE docs", "\n".join(body), "index")


# ---------------------------------------------------------------------- driver

def discover_commands(cli_path):
    """Which commands the CLI has, according to the CLI.

    argparse prints them in a `{init,adopt,...}` group, in the order the author
    put them in, which is a better order than alphabetical: it is roughly the
    order somebody meets them. If that group cannot be found, the hand written
    list is used and said out loud, because silently documenting twelve of
    twenty-five commands is how this page came to describe a version of W4VE
    that stopped existing in August.
    """
    try:
        out = subprocess.run([sys.executable, str(cli_path), "--help"],
                             capture_output=True, text=True, timeout=30,
                             env={**os.environ, "COLUMNS": "200"})
    except (OSError, subprocess.SubprocessError) as err:
        print(f"  ! could not ask the CLI for its commands: {err}", file=sys.stderr)
        return list(COMMANDS)
    found = re.search(r"\{([a-z0-9_,-]{20,})\}", out.stdout or "")
    if not found:
        print("  ! the CLI did not list its commands, using the built in list",
              file=sys.stderr)
        return list(COMMANDS)
    names = [name for name in found.group(1).split(",") if name]
    print(f"the CLI has {len(names)} commands")
    return names


def cli_help(cli_path, commands):
    """Ask the CLI for its own help, one call per command."""
    texts = {}
    for name in [""] + list(commands):
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
    out.mkdir(parents=True)

    # The stylesheet and the fonts beside it. Everything the pages load is
    # served from this directory: the site makes no outside requests.
    shutil.copytree(ASSETS, out / "assets")

    build_nav(pieces)
    langs = load_langs()

    cli = Path(args.cli) if args.cli else None
    if cli is None:
        try:
            cli = fetch_cli(out / ".w4ve.py")
        except Exception as err:                       # noqa: BLE001
            print(f"  ! could not fetch the CLI: {err}", file=sys.stderr)
    commands = list(COMMANDS)
    helps = {}
    if cli and Path(cli).exists():
        commands = discover_commands(cli)
        helps = cli_help(cli, commands)
    if not helps:
        print("  ! no command reference: the CLI could not be run", file=sys.stderr)

    for lang in langs:
        root = out / lang.prefix if lang.prefix else out
        (root / "pieces").mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(render_home(lang, langs, index))
        (root / "profiles.html").write_text(render_profiles(lang, langs, index))
        if helps:
            (root / "commands.html").write_text(
                render_commands(lang, langs, helps, commands))
        (root / "pieces" / "index.html").write_text(
            render_catalog(lang, langs, pieces))
        for piece in pieces.values():
            (root / "pieces" / f"{piece['id']}.html").write_text(
                render_piece(lang, langs, piece, pieces))

    scratch = out / ".w4ve.py"
    if scratch.exists():
        scratch.unlink()

    written = sum(1 for _ in out.rglob("*.html"))
    print(f"wrote {written} pages into {out} "
          f"({', '.join(lg.code for lg in langs)})")

    if args.serve:
        import functools
        import http.server
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(out))
        print("serving on http://localhost:8080, ctrl-c to stop")
        http.server.HTTPServer(("127.0.0.1", 8080), handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
