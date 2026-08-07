<div align="center">

# W4VE

### *Ware 4 Vanilla Experience*

Tools for technical Minecraft servers that do not break vanilla.

[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/keyy8As)
[![Live Map](https://img.shields.io/badge/MineWave-live%20map-brightgreen?logo=minecraft&logoColor=white)](https://mapmine.w4ve.xyz/)

</div>

---

## Start here

*One command installs any of the rest.*

| Project | What it is | Latest |
| --- | --- | --- |
| **[w4ve](https://github.com/CodeW4VE/w4ve)** | One command to install, update and check every piece of the ecosystem. The Python runtime that wraps the server process and keeps MCDR plugins working lands in the same repo. | `0.1.0` |

## Server mods

*Drop the jar in `mods/`. Players install nothing.*

| Project | What it is | Latest |
| --- | --- | --- |
| **[BotInventory](https://github.com/CodeW4VE/BotInventory-Carpet)** | View and manage fake player inventories and ender chests by right-click or command, without stopping the farm. | `1.0.0` |
| **[MankeDoMath](https://github.com/CodeW4VE/MankeDoMath)** | A calculator that **knows what a shulker box is**. Farm rates, item counts and timings without leaving the game, with stacks, shulker boxes, ticks and chunks as real units: `5sb / 2h` works out to items per hour on its own. | `1.1.0` |
| **[MankeList](https://github.com/CodeW4VE/MankeList)** | Material list for whatever you are building: `/ml`, a HUD overlay, and an optional Discord board that tracks what is still missing. | `1.0.0` |
| **[MinimapSync](https://github.com/CodeW4VE/minimap-sync)**<br><sub>fork of [Earthcomputer/minimap-sync](https://github.com/Earthcomputer/minimap-sync)</sub> | Server-side waypoint sync for Xaero's Minimap, kept working on current Xaero releases instead of crashing them. | `1.2.3-w4ve.1` |
| **[RegionCast](https://github.com/CodeW4VE/RegionCast)** | Pull **region files** from another server's world into this one, picked off a map where one tile is one region. Single chunks too, when a whole region is more than you wanted, and the last few updates stay undoable. | `1.0.1` |
| **[RipDeepslate](https://github.com/CodeW4VE/RipDeepslate)** | Deepslate mines **exactly like stone** with a netherite pickaxe, instant with Efficiency V + Haste II. No ghost blocks, no crack animation. | `1.0.0` |
| **[ShapeBoard](https://github.com/CodeW4VE/ShapeBoard)** | Scoreboards for areas of **any shape**, not just boxes. Outline the zone with blocks in the sky, every block broken or placed inside counts, and a per-player sidebar leaderboard appears when you walk in. | `1.7.0` |
| **[WorldEaterNotifier](https://github.com/CodeW4VE/WorldEaterNotifier)** | Watches world eaters and trenchers and pings **Discord** when one stops or gets obstructed, with per-event ping control so you only get the alerts you want. | `1.3.0` |

## Client mods

*For your own instance.*

| Project | What it is | Latest |
| --- | --- | --- |
| **[Beaconator](https://github.com/CodeW4VE/Beaconator)** | Plan a beacon perimeter before you place a single beacon: ring grid from one point, real coverage volumes, and beams shooting up where a beacon is still missing. | `2.2.0` |
| **[WaveMotes](https://github.com/CodeW4VE/WaveMotes)** | Type `:emote:` in chat, pick from a `/`-style popup. Emotes baked into the jar and rendered client-side, plus optional Discord emojis. | `2.0.1` |

## MCDReforged plugins

*Hot-reloadable, no restart.*

| Project | What it is | Latest |
| --- | --- | --- |
| **[ChatBridge](https://github.com/CodeW4VE/ChatBridge)**<br><sub>fork of [TISUnion/ChatBridge](https://github.com/TISUnion/ChatBridge)</sub> | Discord and Minecraft chat bridge: MC players show up as themselves in Discord, with per-player mute and cross-server emotes. | `1.0` |
| **[DigAll](https://github.com/CodeW4VE/DigAll)** | A real grand total of blocks mined for [DiggyScoreboard](https://github.com/Fallen-Breath/DiggyScoreboard), counting offline and historical players too, bots excluded. | `4.2.1` |
| **[PrimeBackup](https://github.com/CodeW4VE/PrimeBackup)**<br><sub>fork of [TISUnion/PrimeBackup](https://github.com/TISUnion/PrimeBackup)</sub> | Deduplicated backups for MCDR. This fork brings back the clickable command buttons that 1.20.5+ clients silently ignore. | `1.13.1-w4ve.1` |
| **[StatsHelper](https://github.com/CodeW4VE/StatsHelper)**<br><sub>fork of [TISUnion/StatsHelper](https://github.com/TISUnion/StatsHelper)</sub> | Minecraft statistics for MCDR, with a UUID and rename de-duplication fix on top of upstream. | `7.5.1-w4ve.1` |

## Bots and services

*Things that run next to the server.*

| Project | What it is | Latest |
| --- | --- | --- |
| **[Discord To-Do Board](https://github.com/CodeW4VE/discord-todo-board)** | A live project board inside a Discord channel, all buttons, no web app. One board or many, optional HTTP webhook. | `1.0.0` |
| **[Schem Converter](https://github.com/CodeW4VE/Schem-Converter)** | Converts `.litematic` files between NBT versions 4, 5, 6 and 7, so old schematics open in newer Litematica and the other way round. | `1.0.0` |
| **[WaveMotes Server](https://github.com/CodeW4VE/WaveMotes-Server)** | The server side: resource-pack generator and chat injector so **everyone**, even vanilla clients, sees the emotes, bridged to Discord across servers. | `2.0.0` |

## In the works

Not released yet. Listed so you know where this is going.

- **w4ve-core** - Shared Java library for W4VE mods: config with hot reload, commands, permissions, Discord boards, and the link to PyW4VE.

## Profiles

Curated sets, so you do not have to pick fifteen mods one by one. `w4ve install --profile <name>` and you are done.

- **Technical survival server** (`technical-survival`, 12 pieces) - A vanilla-behaviour server for people who build farms and perimeters.
- **Technical player client** (`technical-client`, 7 pieces) - What to put in your own instance to play on one of these servers.
- **MineWave** (`minewave`, 43 pieces) - Exactly what runs on the MineWave survival server. Kept honest: if it is not here, it is not on the server.

---

Built for and running on **MineWave**, our private whitelisted server. 
Peek at the world on the [live map](https://mapmine.w4ve.xyz/), or come hang out in the [Discord](https://discord.gg/keyy8As).

<sub>One person maintains all of this. Issues get answered when they get answered.</sub>
