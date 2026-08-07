# registry

The W4VE catalog: what a technical Minecraft server can install, where each
piece comes from, and which pieces refuse to sit next to each other.

Everything else in the ecosystem reads this repo. The [`w4ve`](https://github.com/CodeW4VE/w4ve)
command line downloads `index.json` from here, and so will the docs site.

```
pieces.toml   written by hand, commented, the source of truth
build.py      asks GitHub, Modrinth and PyPI what is actually published
index.json    generated, never edited by hand
```

The published index lives at:

```
https://raw.githubusercontent.com/CodeW4VE/registry/main/index.json
```

## What is in it

71 pieces and 3 profiles. Not a wish list: the catalog was filled by reading
the `mods/` and `plugins/` folders of the servers we actually run, and by
asking Modrinth what each mod really depends on.

- **Ours**, the mods and plugins under CodeW4VE.
- **Forks** we maintain, tagged `<upstream-version>-w4ve.N` so it is obvious
  whose version you are running.
- **External** pieces we depend on, Fabric API and Carpet and the rest. We
  point at their releases, we do not rehost their code.

The three profiles are `technical-survival`, `technical-client` and `minewave`.

## Adding a piece

Edit `pieces.toml`, then:

```sh
python3 build.py --offline   # validate the file, touch nothing
python3 build.py             # fetch releases and write index.json
```

Standard library only, Python 3.9 or newer. A GitHub token in `GH_TOKEN` or
`GITHUB_TOKEN` lifts the 60 requests per hour limit; without one it still
works, slowly.

Both `pieces.toml` and `index.json` go in the same commit. CI runs
`build.py --check` and fails if the index does not match what the sources say.

### Two things that are easy to get wrong

**Only filter by Minecraft version what actually depends on Minecraft.**
Reading version numbers out of a file name says that `PrimeBackup-v1.13.1.pyz`
is for Minecraft 1.13. It is a plugin, it has no Minecraft version at all.

**A release is identified by its version *and* its Minecraft versions.**
Some mods publish the same version number once per Minecraft release: Server
Waypoint has three separate 3.0.3 builds. Key on the number alone and the
catalog starts claiming there is nothing installable on 1.21 while a server is
merrily running exactly that.

## The other scripts

- `apply_github.py` pushes topics, descriptions, homepage and license to the
  repositories from what the catalog says. Dry run by default, and additive:
  it never removes a topic somebody set by hand.
- `render_profile.py` renders the organisation profile page from the catalog,
  so the front page cannot drift from what is really published.

## License

MIT.
