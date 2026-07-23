<div align="center">
  <h1>Magia Exedra Auto Bot</h1>
  <p>An image-recognition-based <strong>Magia Exedra</strong> automation tool for Windows</p>
  <p>Supports Link Raid and Crystalis farming, English/Japanese templates, and multiple resolutions</p>
  <p>
    <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-blue">
    <img alt="Python" src="https://img.shields.io/badge/Python-3.x-blue">
    <img alt="Qt" src="https://img.shields.io/badge/GUI-PySide6-green">
    <img alt="License" src="https://img.shields.io/badge/Use-Game_Assistant-orange">
  </p>
  <p>
    <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  </p>
</div>

---

## Features

| Mode | Description |
|:----:|:------------|
| **Link Raid** | Enters backup requests, refreshes, searches for LV4 or LV6-LV12 teams, clears finished battles, joins fights, and gives likes |
| **Crystalis** | Clicks `play`, waits for results, and uses `retry` to repeat stages |

- Both modes support a configurable stamina-potion count and stop when it is exhausted
- Supports English/Japanese templates at `720p` / `1080p` / `2K` / `4K`
- Compares every numbered variant in a template group against the same frame and clicks only the highest-scoring candidate in the game window
- Stops safely when a normal screen is not recognized within 60 seconds or a battle within 30 minutes
- Checks the game window, resolution, and required templates before starting to avoid obvious misclicks
- Pauses on keyboard activity or large mouse movement and resumes after five seconds of user inactivity
- While awaiting a clickable template, every five-second miss observes only the game client area for two seconds; over 50% changed game pixels skip that recovery click as likely battle animation, otherwise the bot clicks once at its last action position. It then checks whether a declared next step appeared and, if not, redundantly checks and clicks the current step before continuing the five-second cycle
- The GUI can switch between `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` log levels at runtime
- Supports stable/beta update checks; release builds can safely install validated update packages

## Download

Download the complete ZIP from [GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases), extract it, and run `Magia_Exedra_auto.exe` at the root.

> **Do not copy only the EXE.** The distribution also needs `_internal/`, `resource/`, `language/`, and `tools/` beside it.

## Running from source

Install dependencies first, then launch the entry point:

```bash
pip install -r requirements.txt
python main.py
```

See [Wiki · Run from source and build](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建) for full build instructions.

## Quick Start

### Link Raid

1. Leave the game on the main/Lighthouse screen.
2. Under `选择挂机脚本`, select `link raid挂机启动`.
3. Set the level and stamina-potion count.
4. Click `启动：link raid挂机启动`.

> If the selected LV4 or LV6-LV12 battle is unavailable, the bot refreshes the backup-request list and searches again instead of joining another level.
>
> During normal results or finished-battle cleanup, the bot checks for and gives available likes only after successfully clicking `tap_to_countinue`; clicking `joined_battles` itself does not trigger likes.

### Crystalis

1. Select the stage and team, then remain on the screen where clicking `play` starts battle.
2. Under `选择挂机脚本`, select `自动刷晶花，需要在play界面启动`.
3. Set the stamina-potion count.
4. Click `启动：自动刷晶花，需要在play界面启动`.

> Click `停下当前运行的脚本` to request that the current task stop.

## Template Settings

- Selecting a language and resolution switches **automatically**
- The visible Chinese labels `英语` and `日语` correspond to `EN` and `JP`
- `（空）` means that the template pack is currently unavailable
- `刷新列表` generates `720p` / `1080p` / `4K` templates from the original 2K pack
- Derived templates use interpolation suited to real-time game scaling; after upgrading, click `刷新列表` once to rebuild existing derived packs
- The game language and window resolution should match the active template pack

## Before Use

- Supports only windowed Windows x86-64 / AMD64 gameplay
- The game must remain visible and its recognition area unobstructed
- The bot activates the game window and uses the global mouse; keyboard or large mouse activity pauses it, but an individual mouse action already in progress cannot be interrupted midway
- Coordinate scaling supports `720p` / `1080p` / `2K` / `4K`, but recognition still depends on DPI, window size, and template quality
- The JP server can switch to EN in-game and reuse the English templates
- Runtime logs are written to rotating files under `logs`; use `GUI 日志等级` for GUI debug logs, or `MAGIA_LOG_LEVEL=DEBUG` to control the console when running from source
- Release builds run without a console window; use the GUI log panel or files under `logs/` for troubleshooting

## Wiki

Source setup, building, architecture, template maintenance, update security, and development conventions are documented in the Wiki. The Wiki is now multilingual:

| Language | Entry |
|:--------:|:------|
| 简体中文 | [Wiki 首页](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki) |
| English | [Wiki Home (EN)](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/Home_EN) |
| 日本語 | [Wiki ホーム](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/ホーム) |

Chinese Wiki pages:

- [Run from source and build](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建)
- [Architecture](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/项目架构)
- [Template packs and resolutions](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/模板包与分辨率)
- [Automatic updates and releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/自动更新与发布)
- [Development conventions](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/开发约定)

## Acknowledgments

| Contributor | Contribution |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ overall script design and ongoing maintenance |
| **洛殿** | v1.0.0+ partial Japanese assets and resolution-scaling approach<br>v2.0.0+ compute-power support and Japanese assets |
| **智谱AI** | v2.0.0+ fully rewritten and built by GLM-5.2 |

---

> This script is for learning and communication purposes only. Please comply with the game's terms of service. Users are responsible for consequences arising from its use.

## Translation Notice

This page was translated by AI and may contain ambiguities or inaccuracies. For authoritative content, refer to the original [简体中文 README](./README.md).
