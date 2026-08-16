# Architecture

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Overall structure

```text
main.py                      GUI entry and application-level task controller
src/
  click/                     Click layer
    click_action.py          Same-frame template-group matching, coordinate actions, resolution detection
    click_behavior.py        Window recognition, client motion sampling, OpenCV matching, mouse action
    template_confidence.py   Per-PNG thresholds, hot reload, and completeness validation
  workers/                   Automation worker threads
    base.py                  BaseWorker base class, retry_until, timeout constants
    registry.py              ParamSpec / WorkerMeta / @register registry
    link_raid.py             Link Raid flow
    crystalis.py             Crystalis flow
  packs/                     Template pack management
    language_switcher.py     aim junction, pack scanning/selection/validation
    image_scaler.py          Derive other-resolution templates from 2K source
    file_lock.py             Cross-process template mutex
  core/                      Application infrastructure
    app_settings.py          GUI settings persistence
    log_setup.py             Windowed-safe console and rotating-file logging configuration
    input_activity.py        User keyboard/mouse monitoring and automation-input isolation
  update/
    update_check.py          Version checking and safe update installation
resource/                    Icons and per-PNG confidence configuration
language/                    Template pack source directories
tools/ImageMagick/           Asset scaling tool
```

## Call relationships

```text
main.py -> src/workers -> src/click/click_action -> src/click/click_behavior -> game
src/workers/base.py -> src/core/input_activity.py -> Win32 user32
main.py -> src/packs/image_scaler
main.py -> src/update/update_check
```

## main.py

`mywindow(QWidget)` plus `LanguageSwitcherWidget`. It is the GUI entry and application-level task controller:

- Lazily builds one worker and parameter page per `WorkerMeta`; no worker class is hardcoded in the GUI
- `_start_worker()` rejects concurrent tasks, unresolved update-recovery markers, missing game windows, unknown/mismatched client resolution, incomplete required template groups, and invalid parameters; it reads GUI parameters before expanding dynamic required-template paths
- Resolution mismatch is a hard block
- The GUI has a dedicated `logging` handler with a runtime-selectable DEBUG/INFO/WARNING/ERROR/CRITICAL threshold, defaulting to INFO on new installations; the same selection controls the file handler. Worker `signal.emit` messages remain visible as INFO and are mirrored to files with a GUI-deduplication marker
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

During every template wait, each continuous 5-second miss triggers a 2-second observation of the game client. If more than 50% of pixels change, the activity is treated as likely battle animation and only that recovery cycle is skipped. On a stable image, the next step is checked again before a recovery click at the last safe automation position. For flows with explicitly declared next-step templates, either a normal click or a recovery click returns success only after one is recognized. Ordinary templates may be clicked redundantly while the current page remains; fixed safe-position actions are not repeated immediately. The cycle continues until success, timeout, or cancellation.

Each run starts a `UserActivityGuard`. Keyboard input or cumulative large mouse movement pauses template actions until the user has been idle for 5 seconds. Bot mouse input runs inside an automation guard and therefore does not count as user activity; successful automation input also updates the last safe position.

`_run_safely()` holds the cross-process template mutex for the full worker run, rechecks `expected_pack`, handles cancellation/lock timeout/errors, and always calls `_finish()` in `finally`. Concrete workers must route `run()` through `_run_safely()`.

### link_raid.py

Link Raid flow: navigation, backup requests, refresh, joined-battle cleanup, level selection, join/LP handling, battle completion, likes, and return. Level selection compares every supported level and the central number region at the selected candidate. Candidates at 9/10, 10/10, or with an unreadable participant count are skipped; full and already-ended join results are dismissed and rematched. `tap_to_countinue` confirms the result screen only from the `_1/2` text foreground, then clicks a scaled safe bottom-center coordinate and invokes likes after `back` appears. It supports LV4 and LV6-LV12, never substitutes another level, and uses scaled 2K-baseline coordinates for navigation and scrolling.

### crystalis.py

Crystalis flow. It first performs a scaled 2K-baseline wake-up click at `(2000,1000)`, then loops `click_play -> wait_win -> click_retry_or_recover_lp`.

## src/click

### click_action.py

Collects contiguous numbered template variants, compares a group against one shared frame, and selects only the global highest score. Multiple next-step groups can share a frame; fixed-coordinate actions can restrict detection variants and separate recognition from the click position. It also provides raw/scaled coordinate actions and tolerant client-resolution detection.

### click_behavior.py

Window lookup/focus, visible game-window capture, OpenCV matching, client-only motion sampling, and mouse action. Template reads, Gaussian blur, and text-foreground masks are cached by file signature, while one screenshot can serve multiple groups. Normal matching applies the same 3x3 Gaussian blur to screenshot and templates; text mode uses an Otsu foreground mask so `TM_SQDIFF_NORMED` ignores animated backgrounds. Recognition and recovery sampling use only the game client, which must remain visible and unobstructed.

### template_confidence.py

Parses and hot-reloads `resource/template_confidence.txt`. The highest-scoring candidate uses its own PNG threshold; Link Raid's full-image and level-number winners resolve thresholds independently. Missing, duplicate, malformed, or out-of-range entries reject recognition instead of falling back to a global value. Task startup verifies that every PNG in the active pack resolves to a threshold.

## src/packs

### language_switcher.py

`aim/` junction, pack scanning/selection, labels, `active.json`, complete PNG validation, and required-template validation. Complete validation uses Pillow in addition to the standard library.

### image_scaler.py

Uses ImageMagick Triangle filtering to derive 720p/1080p/4K packs from each 2560x1440 source. The current recipe is version 2, which invalidates output from older recipes. Skip requires matching source SHA-256, recipe/tool fingerprint, and target SHA-256. Cleanup removes only files managed by a valid old manifest.

### file_lock.py

Repository-specific `Global\\` Windows mutex shared by switching, scaling, worker runtime leases, update-lock recovery, and the installer.

## src/update/update_check.py

Prerelease-aware update checking and frozen-app updating. Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use `_win64`. Automatic install requires GitHub SHA-256, cancellable size/hash-checked download, safe bounded extraction, AMD64 PE validation, backups, hash verification, rollback/recovery markers, and startup-health handshake.

## src/core

### log_setup.py

Stdlib-only logging configuration called once at `main.py` import, before `QApplication`. When stderr exists, the console defaults to WARNING and `MAGIA_LOG_LEVEL` can override it; `--windowed` builds safely skip a missing console. Before business imports, the file handler reads `settings.json`, defaults to INFO for new installations, and follows the GUI selector. Worker `signal.emit` messages still display directly in the GUI and are mirrored as `magia.runtime` INFO records with a deduplication marker. Pillow inherits the selected log level, so per-PNG-block diagnostics remain available at DEBUG. Retention defaults to seven days, supports 1-365 days, and startup removes only strictly named expired Magia logs while retaining the active log family.

### app_settings.py

Atomically persists automation mode, log level, and log retention to root `settings.json`.

### input_activity.py

Uses Windows `ctypes` to monitor keyboard and mouse activity. Keyboard input or cumulative large mouse movement pauses automation until the user has been idle for 5 seconds. PyAutoGUI operations use a guard context, so the bot's own movements and clicks do not trigger the pause.

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./项目架构).
