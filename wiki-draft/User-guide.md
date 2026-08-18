# User guide

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

This page is for users of the Windows release package. For source setup, packaging, and development, see [Run from source and build](./Run-from-source-and-build) and [Development conventions](./Development-conventions).

## Installation

1. Download the Windows ZIP from [GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases).
2. Extract the complete ZIP; do not copy only `Magia_Exedra_auto.exe`.
3. Verify that `_internal/`, `resource/`, `language/`, and `tools/` are beside the EXE.
4. Run `Magia_Exedra_auto.exe`.

Release builds do not open an extra console. Runtime messages appear in the GUI, and file logs are stored under `logs/` at the program root.

## General preparation

- Only windowed Windows x86-64 / AMD64 gameplay is supported.
- The game window title must be `MadokaExedra`.
- Keep the game visible and do not cover recognition areas with other windows.
- Select the correct game language before choosing a mode and its options.
- The template list is refreshed at startup; initial multi-resolution generation may take some time.
- Resolution is selected automatically from the game client area.

You can adjust language while the template status reports that the game is not detected, but the game must be running before automation starts. Unknown resolution, unavailable matching packs, or missing required templates block startup.

## Link Raid

### Starting screen

Leave the game on the main/Lighthouse screen. Do not enter backup requests first.

### Options

- Level: LV4 or LV6-LV12.
- Stamina potions: the GUI shows the actual allowed count; automation stops after it is exhausted.

### Flow

1. Open quests and Link Raid.
2. Open backup requests and clear finished battles.
3. Refresh and search for the selected level.
4. Join battle and wait for results.
5. Handle available likes after normal results or finished-battle cleanup.
6. Return to backup requests and repeat.

If the selected level is missing or cannot be clicked safely, the bot refreshes and searches again without joining another level. At the same candidate position, level recognition compares every supported level and independently scores the central level-number region. A click occurs only when both classifiers choose the requested level. Candidates at `9/10`, `10/10`, or with an unreadable participant count are skipped safely. A full or already-ended room is dismissed and rematched.

The result screen is confirmed only from the text foreground of `tap_to_countinue_1/2`; medal graphics are not required, and the animated background is ignored. The bot then clicks a resolution-scaled safe position at the bottom center and starts the like flow after `back` is recognized. Clicking `joined_battles` does not trigger likes by itself.

## Crystalis

### Starting screen

Select a stage and team, then remain on the screen where clicking `play` would start battle.

### Options

- Stamina potions: the GUI shows the actual allowed count; automation stops after it is exhausted.

### Flow

1. Click `play` to start battle.
2. Wait for results and click `result`.
3. Click `retry` to begin the next run.
4. Recover stamina according to the setting, or stop when recovery is unavailable.

Crystalis `result` is searched only in the right 50% of the game client. Its per-image entries in `resource/template_confidence.txt` default to 0.85, excluding unrelated left-side matches.

## Templates and resolution

- `EN` and `JP` are supported, and the last language is remembered.
- At task startup, `720p`, `1080p`, `2K`, or `4K` templates are selected from the client size.
- `（空）` means a pack is unavailable. Wait for startup refresh or click `刷新列表`.
- 2K is the source pack; 720p, 1080p, and 4K packs are generated incrementally.
- The JP server can switch to EN in-game and reuse English templates.
- Every logical PNG has its own threshold in `resource/template_confidence.txt`. Saving takes effect on the next recognition attempt; missing or malformed entries block task startup.

Template naming, the `aim` junction, scaling recipes, and integrity validation are documented in [Template packs and resolutions](./Template-packs-and-resolutions).

## Recognition and click safeguards

- Recognition captures only the game client area, excluding the title bar and borders.
- Every numbered variant in a template group is compared against one shared frame; only the highest-scoring candidate is used.
- Before a template click, three samples are taken over 0.6 seconds. All three must exceed the threshold and remain at nearby centers.
- `tap_to_countinue` is a fixed-position action: after three text-foreground matches from `_1/2`, it clicks the safe bottom-center position once and never uses the detected template location.
- A normal screen times out after 60 seconds and battle waiting after 30 minutes.
- Keyboard input or large mouse movement pauses automation; it resumes after five seconds without user input.
- Every five-second miss while waiting for a clickable template triggers a two-second client observation. More than 50% changed pixels is treated as battle animation and skips recovery. On a stable image, the next step is checked again before any recovery click at the last safe automation position.
- For flows with declared next steps, a click succeeds only when a next-step screen is recognized. If the current screen remains, it may be clicked redundantly before waiting again.

These safeguards reduce false clicks caused by one-frame similarities and window decorations, but cannot guarantee correct recognition when the game is obscured, language is wrong, or window size is abnormal.

## Settings and persistence

| Setting | Behavior |
|:--------|:---------|
| Automation mode | Restores the last selected mode at next startup |
| Game language | Remembers the last selection; the actual `aim` target remains authoritative |
| Log level | Defaults to `INFO` and controls GUI debug records and file logs |
| Log retention | Defaults to seven days, supports 1-365 days, and cleans expired logs at startup |
| `更新至 beta 版` | Selected by default in beta builds; clear it to check only stable versions |

`清理过时日志` immediately applies the current retention period. The active session log and its rotations are always retained.

## Log levels

| Level | Recommended use |
|:------|:----------------|
| `INFO` | Normal use and complete automation flow |
| `DEBUG` | Reproducing recognition issues with template scores and matching details |
| `WARNING` | Warnings, errors, and critical errors only |
| `ERROR` | Errors and critical errors only |
| `CRITICAL` | Critical errors only |

Automation messages always appear in the GUI as INFO. INFO/DEBUG also write them to files; WARNING and higher may produce an empty file when no matching problem occurs.

## Troubleshooting

### Game not detected

1. Verify that the game has finished launching.
2. Verify that the window title is `MadokaExedra`.
3. Ensure the game is not minimized.
4. Restart the tool so startup detection runs again.

### Templates are empty

1. Wait for the first template scaling operation to finish.
2. Click `刷新列表`.
3. Verify that `language/` and `tools/` were fully extracted.
4. Check whether security software quarantined `tools/ImageMagick/magick.exe`.

### Resolution mismatch

Use a supported 16:9 window resolution and avoid extreme DPI/window scaling. A limited size tolerance is allowed, but unknown or clearly mismatched client sizes block startup.

### Missing recognition or wrong click

1. Keep the game fully visible and unobstructed.
2. Match game language to template language.
3. Start the mode from its required screen.
4. Select `DEBUG`, reproduce once, and stop.
5. Keep the newest `logs/magia_*.log` and report game language, client resolution, mode, and the failing step.

### Empty log file

Check the selected level. `WARNING`, `ERROR`, or `CRITICAL` may legitimately remain empty when no matching event occurs; use `INFO` for normal flow records.

## Further reading

- [Run from source and build](./Run-from-source-and-build)
- [Template packs and resolutions](./Template-packs-and-resolutions)
- [Architecture](./Architecture)
- [Development conventions](./Development-conventions)

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./首页).
