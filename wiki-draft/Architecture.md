# Architecture

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Overall structure

```text
main.py                      GUI entry and application-level task controller
src/
  click/                     Click layer
    click_action.py          Same-frame template-group matching, coordinate actions, resolution detection
    click_behavior.py        Window recognition, client motion sampling, OpenCV matching, mouse action
  workers/                   Automation worker threads
    base.py                  BaseWorker base class, retry_until, timeout constants
    registry.py              ParamSpec / WorkerMeta / @register registry
    link_raid.py             Link Raid flow
    crystalis.py             Crystalis flow
  packs/                     Template pack management
    language_switcher.py     aim junction, pack scanning/selection/validation
    image_scaler.py          Derive other-resolution templates from 2K source
    file_lock.py             Cross-process template mutex
  update_check.py            Version checking and safe update installation
  log_setup.py               Windowed-safe console and rotating-file logging configuration
  input_activity.py          User keyboard/mouse monitoring and automation-input isolation
resource/                    Icons and other resources
language/                    Template pack source directories
tools/ImageMagick/           Asset scaling tool
```

## Call relationships

```text
main.py -> src/workers -> src/click/click_action -> src/click/click_behavior -> game
src/workers/base.py -> src/input_activity.py -> Win32 user32
main.py -> src/packs/image_scaler
main.py -> src/update_check
```

## main.py

`mywindow(QWidget)` plus `LanguageSwitcherWidget`. It is the GUI entry and application-level task controller:

- Lazily builds one worker and parameter page per `WorkerMeta`; no worker class is hardcoded in the GUI
- `_start_worker()` rejects concurrent tasks, unresolved update-recovery markers, missing game windows, unknown/mismatched client resolution, incomplete required template groups, and invalid parameters; it reads GUI parameters before expanding dynamic required-template paths
- Resolution mismatch is a hard block
- The GUI has a dedicated `logging` handler with a runtime-selectable DEBUG/INFO/WARNING/ERROR/CRITICAL threshold, defaulting to WARNING; worker `signal.emit` user messages are unaffected by this filter
- New builds use PyInstaller `--windowed` and no longer show an empty companion console; compatibility with old console-mode builds hides an existing console
- `closeEvent()` uses one shared 12-second deadline to stop/wait for workers, scaling, update checks, and update preparation
- Update signals include a task ID so stale thread results are ignored
- Source-mode automatic checks log the Release URL; only manual checks open it

`main.py` does not contain Link Raid or Crystalis flow logic.

## src/workers

Automation worker threads. Mode code is independent, but only one worker can run in one GUI process; automation, scaling, and update installation are mutually exclusive.

### registry.py

`ParamSpec` describes GUI parameters. `WorkerMeta` contains `name`, `label`, `worker_class`, `params`, `start_hint`, and `required_templates`. Required template paths are relative to the pack root and omit the `_<number>.png` suffix. Paths may contain placeholders such as `{level_choice}`, but each placeholder must reference a declared `ParamSpec.key`. These paths cover startup-critical groups; optional best-effort groups need not block startup.

Adding a mode requires a no-argument-constructible `BaseWorker` subclass decorated with `@register`, plus an import in `src/workers/__init__.py`.

### base.py

`BaseWorker(QThread)`, `retry_until()`, `RETRY_TIMEOUT=60`, and `BATTLE_TIMEOUT=1800`. Per-worker state is `_active` plus `_stop_event`; `start()` refuses restart while the old thread still runs.

During every template wait, each continuous 5-second miss triggers a 2-second observation of the game client. If more than 50% of pixels change, the activity is treated as likely battle animation and only that recovery cycle is skipped. Otherwise, one recovery click is made at the last safe automation position. For flows with explicitly declared next-step templates, either a normal click or a recovery click returns success only after one of those templates is recognized; while the current template remains, it is clicked redundantly. The 5-second cycle then continues until success, timeout, or cancellation.

Each run starts a `UserActivityGuard`. Keyboard input or cumulative large mouse movement pauses template actions until the user has been idle for 5 seconds. Bot mouse input runs inside an automation guard and therefore does not count as user activity; successful automation input also updates the last safe position.

`_run_safely()` holds the cross-process template mutex for the full worker run, rechecks `expected_pack`, handles cancellation/lock timeout/errors, and always calls `_finish()` in `finally`. Concrete workers must route `run()` through `_run_safely()`.

### link_raid.py

Link Raid flow: navigation, backup requests, refresh, joined-battle cleanup, level selection, join/LP handling, battle completion, likes, and return. Level selection first locates the selected template's best candidate, then compares every supported level near that same position and independently compares the central level-number region. It clicks only when both the full image and number region classify as the selected level; every level template is therefore a startup-required competitor. Normal results and joined-battle cleanup invoke the shared like flow only after `tap_to_countinue` succeeds; clicking `joined_battles` itself does not trigger likes. It supports LV4 and LV6-LV12. If the selected level is missing or cannot be clicked, it refreshes and searches again instead of joining another level. Initial navigation and scrolling use scaled 2K-baseline coordinates.

### crystalis.py

Crystalis flow. It first performs a scaled 2K-baseline wake-up click at `(2000,1000)`, then loops `click_play -> wait_win -> click_retry_or_recover_lp`.

## src/click

### click_action.py

Collects contiguous numbered template variants, compares the entire group against one shared frame, and finds or clicks only the globally highest-scoring candidate. It also provides raw/scaled coordinate actions and tolerant client-resolution detection.

### click_behavior.py

Window lookup/focus, visible game-window capture, OpenCV matching, client-only motion sampling, and mouse action. Before matching, the same 3x3 Gaussian blur is applied to both screenshot and templates, followed by `TM_SQDIFF_NORMED`; a match requires a score strictly `> 0.8`. Template recognition captures the visible game window, while recovery-motion detection samples only the game client. The game must remain visible and unobstructed.

## src/packs

### language_switcher.py

`aim/` junction, pack scanning/selection, labels, `active.json`, complete PNG validation, and required-template validation. Complete validation uses Pillow in addition to the standard library.

### image_scaler.py

Uses ImageMagick Triangle filtering to derive 720p/1080p/4K packs from each 2560x1440 source. The current recipe is version 2, which invalidates output from older recipes. Skip requires matching source SHA-256, recipe/tool fingerprint, and target SHA-256. Cleanup removes only files managed by a valid old manifest.

### file_lock.py

Repository-specific `Global\\` Windows mutex shared by switching, scaling, worker runtime leases, update-lock recovery, and the installer.

## src/update_check.py

Prerelease-aware update checking and frozen-app updating. Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use `_win64`. Automatic install requires GitHub SHA-256, cancellable size/hash-checked download, safe bounded extraction, AMD64 PE validation, backups, hash verification, rollback/recovery markers, and startup-health handshake.

## src/log_setup.py

Stdlib-only logging configuration called once at `main.py` import, before `QApplication`. When stderr exists, the console handler defaults to WARNING and `MAGIA_LOG_LEVEL` can override its level; `--windowed` builds safely skip the console handler when stderr is absent. A rotating DEBUG file handler writes to `logs/`. `main.py` separately installs a GUI handler that defaults to WARNING and supports runtime level switching. Worker `signal.emit` calls remain an unfiltered user-message channel, unaffected by the GUI handler threshold and not replaced by `logging`; runtime `print()` calls have been migrated to `logging.getLogger(__name__)`.

## src/input_activity.py

Uses Windows `ctypes` to monitor keyboard and mouse activity. Keyboard input or cumulative large mouse movement pauses automation until the user has been idle for 5 seconds. PyAutoGUI operations use a guard context, so the bot's own movements and clicks do not trigger the pause.

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./项目架构).
