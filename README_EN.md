<div align="center">
  <h1>Magia Exedra Auto Bot</h1>
  <p>An image-recognition-based <strong>Magia Exedra</strong> Windows game automation script</p>
  <p>Supports both Link Raid and Crystalis auto-farming modes, with language/resolution switching and automatic asset scaling</p>
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
- Before starting, detects the game window's client-area resolution and compares it with the selected template pack using a tolerant margin (accommodates small drift from title bar / borders / DPI scaling); logs a warning on mismatch
- Stop button can interrupt any farming task at any time
- The two farming modes are mutually exclusive; template switching and refresh are disabled while a task is running
- Select a farming script from a dropdown; only that script's parameters are shown, so new modes do not keep extending the window vertically
- Includes a `检查更新` entry; the button is currently reserved because no version source has been configured
- Automatically stops safely if a normal screen is not recognized within 60 seconds or a battle within 30 minutes
- Recognition captures only the game window; missing windows or invalid templates are reported instead of crashing
- Language / resolution switching (supports English, Japanese; multi-resolution assets auto-scaled)
- One-click scaling of 2K (2560×1440) source assets to 720p / 1080p / 4K

---

## How It Works

| Module | Technical approach |
|:-----:|:---------|
| Image recognition | OpenCV `TM_SQDIFF_NORMED`, match threshold `0.8` |
| Click actions | PyAutoGUI (move-then-click, otherwise the game rejects the input) |
| Window management | pywinctl (find window by title `MadokaExedra`, read client-area resolution) |
| GUI | PySide6 |
| Asset scaling | ImageMagick (`tools/ImageMagick/magick.exe`) |
| Template switching | Windows directory junction; `aim/` points to the real pack under `language/` |

### Workflow

```
main.py (GUI entry; only starts/stops workers and passes params)
    │
    ├── workers/LinkRaidWorker ──► click_action ──► click_behavior ──► Game
    │   (Link Raid)               (template iter + coords) (match + click + window)
    │
    ├── workers/CrystalisWorker ──► click_action ──► click_behavior ──► Game
    │   (Crystalis)
    │
    └── LanguageSwitcherWidget
          ├── language_switcher (junction management)
          └── image_scaler (2K -> other resolutions)
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
pip install pyautogui PySide6 opencv-python pywinctl Pillow

# Run
python main.py

# Build an exe
pyinstaller -D -i resource/main.ico main.py
```

---

## Operating Instructions

### 1. Link Raid farming

Must be started on the game's main screen (Lighthouse screen)

- Select `link raid挂机启动` from the script dropdown
- Select the level to farm (LV6 ~ LV12)
- Set the stamina-potion drink count (0 ~ 10)
- Click "**启动：link raid挂机启动**" (start the selected Link Raid script)

### 2. Crystalis farming

Must be started on the team-select screen (the screen where clicking `play` enters battle)

- Select `自动刷晶花，需要在play界面启动` from the script dropdown
- Set the stamina-potion drink count (0 ~ 8)
- Click "**启动：自动刷晶花，需要在play界面启动**" (start the selected Crystalis script)

### 3. Language / resolution switching

- After selecting a language and resolution in the dropdown, it **switches automatically** — no extra confirm button
- The language dropdown shows Chinese names (English / Japanese), while the item data holds the real code
- Empty template packs are shown as "（空）" and switching is rejected

### 4. Refresh list

Automatically scales the 2K (2560×1440) source assets to other resolutions:

| Source resolution | → Target | Scale |
|:--------:|:----------:|:----:|
| 2560×1440 | 1280×720 | 0.5x (downscale) |
| 2560×1440 | 1920×1080 | 0.75x (downscale) |
| 2560×1440 | 3840×2160 | 1.5x (upscale) |

> 720p / 1080p are downscaled and of good quality; 4K is upscaled (non-integer resampling) and slightly softer.
> A target is generated when missing or when its 2K source content changes. Derived templates removed from the source pack are cleaned automatically. The list refreshes after scaling.

### 5. Check for updates

- Clicking `检查更新` reports the current update status in the log
- No update source is configured yet, so this button is currently only an entry point for a future GitHub Releases or update-service integration

---

## Notes

> **Testing status:** The latest changes to thread stopping, wait timeouts, game-window capture, incremental template scaling, and game-window resolution detection have only passed syntax, import, and static diff checks. They have not yet undergone extended end-to-end testing against the live game. Monitor a short run before leaving the bot unattended.

- The **game window must be in the foreground and unobstructed**; the bot window itself can remain in the background
- The first click of Link Raid uses **hardcoded coordinates** (`2000,1000` → `2400,1200`, 2K baseline); they auto-scale to the active resolution, so 720p / 1080p / 2K / 4K all work
- The game must run in **16:9** windowed mode, and the template's language and resolution must match the game
- The JP server can be switched to EN in-game to reuse the English templates without re-capturing screenshots

---

## Project Structure

```
Magia_Exedra_auto/
├── main.py                  # GUI entry: selects scripts, switches parameter pages, starts/stops workers, and passes params
├── src/                     # Source package
│   ├── workers/             # automation run-logic package (decoupled from the GUI)
│   │   ├── registry.py      # Registry: workers self-describe params via @register, GUI auto-generates widgets
│   │   ├── base.py          # worker base class (run/stop state, retry and timeout stop)
│   │   ├── link_raid.py     # Link Raid farming flow
│   │   └── crystalis.py     # Crystalis farming flow
│   ├── click/               # Click module package
│   │   ├── click_action.py  # High-level click actions (template iteration, coordinate clicks, drags, resolution detection)
│   │   └── click_behavior.py# Low-level ops (screenshot, match, click, window focus, client-area size)
│   └── packs/               # Template-pack management (stdlib-only, runnable standalone)
│       ├── language_switcher.py # Language/resolution switching (junction management)
│       └── image_scaler.py  # Asset scaling (2K -> other resolutions)
├── language/                # Template pack directory
│   ├── EN/                  # English
│   │   ├── EN_1280x720/     # 720p (generated by scaling)
│   │   ├── EN_1920x1080/    # 1080p (generated by scaling)
│   │   ├── EN_2560x1440/    # 2K source assets
│   │   └── EN_3840x2160/    # 4K (generated by scaling)
│   └── JP/                  # Japanese
│       └── ...
├── aim/                     # Runtime junction, points to the currently used template pack
├── resource/
│   └── main.ico             # Program icon
├── tools/
│   └── ImageMagick/         # Portable ImageMagick (used for asset scaling)
└── AGENTS.md                # Project notes for AI assistants (development reference)
```

### Core Conventions

- **Return value convention**: `2` = success / found / clicked; `1` = not found / keep trying. Not booleans.
- **Template numbering**: `click_item_with_result` tries `<name>_1.png`, `<name>_2.png`... incrementing until a file does not exist; to add a variant, just drop in the next-numbered image.
- **Run/stop state**: each worker thread keeps its own `_active` (whether it is running) and `_stop_event` (the GUI stop event); the global `guaji` flags are gone. `stop()` is safe to call on a not-yet-started or already-finished thread, and one thread object can be restarted repeatedly.

---

## Acknowledgments

| Contributor | Contribution |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ overall script design and ongoing maintenance |
| **洛殿** | v1.0.0+ partial Japanese assets and resolution-scaling approach<br>v2.0.0+ compute-power support and Japanese assets |
| **智谱AI** | v2.0.0+ fully rewritten and built by GLM-5.2 |

---

## Supplementary Notes

This script **cannot run on a mobile phone** (it cannot be controlled via ADB). The game refuses to run when it detects an ADB connection, and the anti-cheat mechanism restricts keyboard-input scripts. The PC approach based on window image recognition is currently the lowest-barrier compromise.

> This script is for learning and communication purposes only. Please comply with the game's terms of service. We are not responsible for any consequences arising from the use of this script.

---

## Translation Notice

This page was translated by AI and may contain ambiguities or inaccuracies. For authoritative content, please refer to the original [简体中文 README](./README.md).
