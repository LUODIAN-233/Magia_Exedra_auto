[简体中文](./README.md) · [English](./README_EN.md) · [日本語](./README_JP.md)

<div align="center">

# Magia Exedra Auto Bot

An image-recognition-based **Magia Exedra**（圆哆啦） Windows game automation script

Supports both Link Raid and Crystalis auto-farming modes, with language/resolution switching and automatic asset scaling

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![Qt](https://img.shields.io/badge/GUI-PySide6-green)
![License](https://img.shields.io/badge/Use-Game_Assistant-orange)

</div>

---

## Feature Overview

### Link Raid Auto-farming

> Starting screen: the game's main screen (Lighthouse screen)

- Automatically enters the `backup_requests` screen, refreshes and searches for teams of the specified level
- Automatically scrolls down the list when the target level is not found, up to 4 times
- Automatically clears finished battles (joined battles)
- Automatically gives a "like" after a battle ends
- Configurable stamina-potion usage count (**0 ~ 10 times**)
- Supports LV6 ~ LV12 level selection

### Crystalis Auto-farming

> Starting screen: the team-select screen (the screen where clicking `play` enters battle)

- Automatically repeats stages; clicks `retry` after each battle to continue
- Configurable stamina-potion usage count (**0 ~ 8 times**)
- Automatically stops when stamina is exhausted and potions are used up

### General Features

- Brings the game window to the foreground on startup
- Stop button can interrupt any farming task at any time
- Language / resolution switching (supports English, Japanese; multi-resolution assets auto-scaled)
- One-click scaling of 720p source assets to 1080p / 1440p / 4K

---

## How It Works

| Module | Technical approach |
|:-----:|:---------|
| Image recognition | OpenCV `TM_SQDIFF_NORMED`, match threshold `0.8` |
| Click actions | PyAutoGUI (move-then-click, otherwise the game rejects the input) |
| Window management | pywinctl (find window by title `MadokaExedra`) |
| GUI | PySide6 |
| Asset scaling | ImageMagick (`tools/ImageMagick/magick.exe`) |
| Template switching | Windows directory junction; `aim/` points to the real pack under `language/` |

### Workflow

```
main.py (GUI + worker threads)
    │
    ├── WorkThread_1 ──► click_action ──► click_behavior ──► Game
    │   (Link Raid)      (template iteration  (match + click + window)
    │                     + coordinates)
    │
    ├── WorkThread_2 ──► click_action ──► click_behavior ──► Game
    │   (Crystalis)
    │
    └── LanguageSwitcherWidget
          ├── language_switcher (junction management)
          └── image_scaler (720p → higher resolutions)
```

---

## Requirements

| Item | Requirement |
|:----:|:-----|
| OS | Windows |
| Game | Magia Exedra, window title `MadokaExedra`, running in **16:9** windowed mode |
| Python | 3.x |

---

## Usage

### Option 1: Use a release build (recommended)

Download a release, extract it, and run the corresponding EXE (all dependencies are bundled).

### Option 2: Run from source / build it yourself

```bash
# Install dependencies (the project has no requirements.txt; install manually)
pip install pyautogui PySide6 opencv-python pywinctl

# Run
python main.py

# Build an exe
pyinstaller -D -i resource/main.ico main.py
```

---

## Operating Instructions

### 1. Link Raid farming

Must be started on the game's main screen (Lighthouse screen)

- Select the level to farm (LV6 ~ LV12)
- Set the stamina-potion drink count (0 ~ 10)
- Click "**link raid挂机启动**" (the Link Raid start button)

### 2. Crystalis farming

Must be started on the team-select screen (the screen where clicking `play` enters battle)

- Set the stamina-potion drink count (0 ~ 8)
- Click "**自动刷晶花，需要在play界面启动**" (the Crystalis start button)

### 3. Language / resolution switching

- After selecting a language and resolution in the dropdown, it **switches automatically** — no extra confirm button
- The language dropdown shows Chinese names (English / Japanese), while the item data holds the real code
- Empty template packs are shown as "（空）" and switching is rejected

### 4. Refresh list

Automatically scales the 720p source assets to other resolutions:

| Source resolution | → Target | Scale |
|:--------:|:----------:|:----:|
| 1280×720 | 1920×1080 | 1.5x |
| 1280×720 | 2560×1440 | 2x |
| 1280×720 | 3840×2160 | 3x |

> Existing target files are skipped; delete a target file to force regeneration.

---

## Notes

- The **game window must be in the foreground**; the bot can run in the background (being covered by other windows does not matter)
- The first click of Link Raid uses **hardcoded coordinates** (`1000,500` → `1200,600`), which only works at 1280×720
- After switching resolution, the first Link Raid click needs manual adjustment (click the bottom-right corner)
- The game must run in **16:9** windowed mode, and the template language must match the game language
- The JP server can be switched to EN in-game to reuse the English templates without re-capturing screenshots

---

## Project Structure

```
Magia_Exedra_auto/
├── main.py                  # Entry: GUI + two worker threads + language switcher widget
├── click_action.py          # High-level click actions (template iteration, coordinate clicks, drags)
├── click_behavior.py        # Low-level ops (screenshot, match, click, window focus)
├── language_switcher.py     # Language/resolution switching (junction management)
├── image_scaler.py          # Asset scaling (720p → other resolutions)
├── language/                # Template pack directory
│   ├── EN/                  # English
│   │   ├── EN_1280x720/     # 720p source assets
│   │   ├── EN_1920x1080/    # 1080p (generated by scaling)
│   │   ├── EN_2560x1440/    # 1440p (generated by scaling)
│   │   └── EN_3840x2160/    # 4K (generated by scaling)
│   └── JP/                  # Japanese
│       └── ...
├── aim/                     # Runtime junction, points to the currently used template pack
├── screenshot/              # Runtime screenshot directory
├── resource/
│   └── main.ico             # Program icon
├── tools/
│   └── ImageMagick/         # Portable ImageMagick (used for asset scaling)
└── AGENTS.md                # Project notes for AI assistants (development reference)
```

### Core Conventions

- **Return value convention**: `2` = success / found / clicked; `1` = not found / keep trying. Not booleans.
- **Template numbering**: `click_item_with_result` tries `<name>_1.png`, `<name>_2.png`... incrementing until a file does not exist; to add a variant, just drop in the next-numbered image.
- **Stop flags**: `guaji_1` / `guaji_2` are global variables, unlocked, mutated by the `stop_any` thread and read by worker threads.

---

## Acknowledgments

| Contributor | Contribution |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ overall script design and ongoing maintenance |
| **洛殿** | v1.0.0+ partial Japanese assets and resolution-scaling approach |
| **智谱AI** | v2.0.0 fully rewritten and built by GLM-5.2 |

---

## Supplementary Notes

This script **cannot run on a mobile phone** (it cannot be controlled via ADB). The game refuses to run when it detects an ADB connection, and the anti-cheat mechanism restricts keyboard-input scripts. The PC approach based on window image recognition is currently the lowest-barrier compromise.

> This script is for learning and communication purposes only. Please comply with the game's terms of service. We are not responsible for any consequences arising from the use of this script.

---

## Translation Notice

This page was translated by AI and may contain ambiguities or inaccuracies. For authoritative content, please refer to the original [简体中文 README](./README.md).
