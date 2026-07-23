# Architecture

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Overall structure

```text
main.py                      GUI entry and application-level task controller
src/
  click/                     Click layer
    click_action.py          Numbered-template iteration, coordinate actions, resolution detection
    click_behavior.py        Window lookup/focus, screenshot, OpenCV matching, mouse action
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
  log_setup.py               Logging configuration (console + rotating file), called at main.py import
resource/                    Icons and other resources
language/                    Template pack source directories
tools/ImageMagick/           Asset scaling tool
```

## Call relationships

```text
main.py -> src/workers -> src/click/click_action -> src/click/click_behavior -> game
main.py -> src/packs/image_scaler
main.py -> src/update_check
```

## main.py

`mywindow(QWidget)` plus `LanguageSwitcherWidget`. It is the GUI entry and application-level task controller:

- Lazily builds one worker and parameter page per `WorkerMeta`; no worker class is hardcoded in the GUI
- `_start_worker()` rejects concurrent tasks, unresolved update-recovery markers, missing game windows, unknown/mismatched client resolution, incomplete required template groups, and invalid parameters
- Resolution mismatch is a hard block
- `closeEvent()` uses one shared 12-second deadline to stop/wait for workers, scaling, update checks, and update preparation
- Update signals include a task ID so stale thread results are ignored
- Source-mode automatic checks log the Release URL; only manual checks open it

`main.py` does not contain Link Raid or Crystalis flow logic.

## src/workers

Automation worker threads. Mode code is independent, but only one worker can run in one GUI process; automation, scaling, and update installation are mutually exclusive.

### registry.py

`ParamSpec` describes GUI parameters. `WorkerMeta` contains `name`, `label`, `worker_class`, `params`, `start_hint`, and `required_templates`. Required template paths are relative to the pack root and omit the `_<number>.png` suffix; they cover startup-critical groups. Optional best-effort groups need not block startup.

Adding a mode requires a no-argument-constructible `BaseWorker` subclass decorated with `@register`, plus an import in `src/workers/__init__.py`.

### base.py

`BaseWorker(QThread)`, `retry_until()`, `RETRY_TIMEOUT=60`, and `BATTLE_TIMEOUT=1800`. Per-worker state is `_active` plus `_stop_event`; `start()` refuses restart while the old thread still runs.

`_run_safely()` holds the cross-process template mutex for the full worker run, rechecks `expected_pack`, handles cancellation/lock timeout/errors, and always calls `_finish()` in `finally`. Concrete workers must route `run()` through `_run_safely()`.

### link_raid.py

Link Raid flow: navigation, backup requests, refresh, joined-battle cleanup, level selection, join/LP handling, battle completion, likes, and return. Initial navigation and scrolling use scaled 2K-baseline coordinates.

### crystalis.py

Crystalis flow. It first performs a scaled 2K-baseline wake-up click at `(2000,1000)`, then loops `click_play -> wait_win -> click_retry_or_recover_lp`.

## src/click

### click_action.py

Numbered-template iteration, raw/scaled coordinate actions, and tolerant client-resolution detection.

### click_behavior.py

Window lookup/focus, visible desktop-region screenshot, OpenCV matching, and mouse action. The game must remain visible and unobstructed.

## src/packs

### language_switcher.py

`aim/` junction, pack scanning/selection, labels, `active.json`, complete PNG validation, and required-template validation. Complete validation uses Pillow in addition to the standard library.

### image_scaler.py

Derives 720p/1080p/4K packs from each 2560x1440 source. Skip requires matching source SHA-256, recipe/tool fingerprint, and target SHA-256. Cleanup removes only files managed by a valid old manifest.

### file_lock.py

Repository-specific `Global\\` Windows mutex shared by switching, scaling, worker runtime leases, update-lock recovery, and the installer.

## src/update_check.py

Prerelease-aware update checking and frozen-app updating. Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use `_win64`. Automatic install requires GitHub SHA-256, cancellable size/hash-checked download, safe bounded extraction, AMD64 PE validation, backups, hash verification, rollback/recovery markers, and startup-health handshake.

## src/log_setup.py

Stdlib-only logging configuration called once at `main.py` import, before `QApplication`. The console handler defaults to WARNING (so image-recognition retries do not spam), while a rotating DEBUG file handler writes to `logs/`. The `MAGIA_LOG_LEVEL` environment variable overrides the console level. Worker `signal.emit` calls remain the user-facing GUI log channel and are not replaced by `logging`; runtime `print()` calls have been migrated to `logging.getLogger(__name__)`.

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./项目架构).
