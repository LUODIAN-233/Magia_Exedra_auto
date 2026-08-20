# AGENTS.md

Windows-only game-automation bot for **Magia Exedra** (game window title `MadokaExedra`). Image-recognition clicking uses OpenCV `TM_SQDIFF_NORMED` plus PyAutoGUI, with a PySide6 GUI. Code comments and GUI prose are Chinese-first. `README.md` is authoritative; `README_EN.md` and `README_JP.md` are maintained translations.

## Running / building

- Run: `python main.py`. The entry point changes cwd to the script/exe directory so relative runtime paths resolve. Startup calls `language_switcher.ensure_active()`, which restores or creates the `aim/` junction.
- Build: `pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py`. `--windowed` prevents an empty console window from opening beside the GUI. The built entry is named `Magia_Exedra_auto.exe` via `-n`; this is the executable shipped in releases. This creates only the PyInstaller onedir output; a distributable package must also place `resource/`, `language/`, and `tools/` beside `Magia_Exedra_auto.exe`.
- In frozen mode, `OPENCV_SKIP_PYTHON_LOADER=1` must be set before anything imports `cv2`.
- **DPI-sensitive import order:** keep `src.workers` lazy. Startup must remain `QApplication(...) -> mywindow() -> get_worker_registry()`. Importing workers earlier imports PyAutoGUI and may prevent Qt from setting Windows DPI awareness. `main.py` calls `log_setup.configure_logging()` at module import, before `QApplication`; this is stdlib-only and safe, and must stay before any business module import so all loggers are captured.
- Runtime dependencies are declared in `requirements.txt` (`pyautogui`, `PySide6`, `opencv-python`, `numpy`, `pywinctl`, `Pillow`); install with `pip install -r requirements.txt`. Release builds use `pip install -r requirements-build.txt`, which includes the runtime dependencies and pins the verified PyInstaller 6.21.0 build tool. Runtime versions remain intentionally unpinned until a complete tested environment lock is recorded; do not invent partial pins. Scaling uses committed `tools/ImageMagick/magick.exe` or `magick` on PATH.
- Standard-library regression tests live under `tests/`; run `python -B -m unittest discover -s tests -v`. There is no lint/typecheck config or CI. Also run every applicable non-game check: Python compile/import checks, worker registry and template validation, update ZIP/extraction checks, lock/updater checks, AMD64 PE validation, and packaged-app smoke start.

## Architecture

Mode-specific automation lives in `src/workers/`. `main.py` is the GUI entry and application-level task controller: it constructs workers, injects parameters, coordinates automation/scaling/update mutual exclusion, performs startup checks, orchestrates updates, and handles cooperative shutdown. It does not contain Link Raid or Crystalis flow logic.

- `main.py` - `mywindow(QWidget)` plus `LanguageSwitcherWidget` and a modal `SettingsDialog`. It lazily builds one worker and parameter page per `WorkerMeta`; no worker class is hardcoded in the GUI. `_start_worker()` rejects concurrent tasks, unresolved update-recovery markers, missing game windows, unknown client resolution, unavailable matching packs, incomplete required template groups, and invalid parameters. It automatically switches `aim/` to the closest usable resolution for the selected language, then independently rechecks the match. It reads parameters before expanding dynamic required-template paths. The main window exposes one `设置` entry; log level, 1–365-day retention, expired-log cleanup, beta channel, and manual update check live in the dialog. The selected worker mode, log level, and retention persist in root `settings.json`; mode persistence uses stable `WorkerMeta.name` values. The log selector controls both GUI debug records and the rotating file handler, while worker user messages remain unfiltered. Prerelease builds initialize the beta-update checkbox as selected before the automatic update check starts. Startup completes the automatic update check before scheduling derived-template scaling: no update, check failure, source mode, or declining the prompt continues to scaling, while accepting an update keeps scaling deferred unless preparation fails or is cancelled. Frozen console-mode compatibility hides an existing console, while new builds use `--windowed`. `closeEvent()` uses one shared 12-second deadline to stop/wait for workers, scaling, update checks, and update preparation. Update signals include a task ID so stale thread results are ignored. Source-mode automatic checks log the Release URL; only manual checks open it.
- `src/workers/registry.py` - `ParamSpec` describes GUI parameters. `WorkerMeta` contains `name`, `label`, `worker_class`, `params`, `start_hint`, and `required_templates`. Required template paths are relative to the pack root, omit `_<number>.png`, and may contain placeholders such as `{level_choice}` referencing declared `ParamSpec.key` values. They cover startup-critical groups; optional best-effort groups need not block startup. Adding a mode requires a no-argument-constructible `BaseWorker` subclass decorated with `@register`, plus an import in `src/workers/__init__.py`.
- `src/workers/base.py` - `BaseWorker(QThread)`, `retry_until()`, `RETRY_TIMEOUT=60`, and `BATTLE_TIMEOUT=1800`. Per-worker state is `_active` plus `_stop_event`; `start()` refuses restart while the old thread still runs. Each run starts a `UserActivityGuard`, tracks the last automation position, and pauses template actions while the user is active. `_click_until()` polls normal steps every 0.2 seconds and battle waits every 0.5 seconds. During a click-template wait, every 5-second miss observes the game client for 2 seconds: more than 50% changed pixels skips only that recovery cycle as likely battle animation. Before any last-position recovery click it rechecks all declared next-step groups from one shared frame. Normal template-position actions may use the last safe automation position and redundantly click a still-visible current template. Fixed safe-coordinate actions are different: they must freshly recognize the current page, click only up to `fixed_click_limit`, never use last-position recovery, and cannot accept a next-step match until at least one confirmed current-page click has occurred. The 5-second cycle continues until success, timeout, or cancellation. `_run_safely()` holds the cross-process template mutex for the full worker run, rechecks `expected_pack`, handles cancellation/lock timeout/errors, and always calls `_finish()` in `finally`. Concrete workers must route `run()` through `_run_safely()`.
- `src/workers/link_raid.py` - Link Raid flow: navigation, backup requests, refresh, joined-battle cleanup, level selection, join/LP handling, battle completion, likes, and return. Level selection searches only the normalized request-list region, evaluates multiple selected-level candidates, and compares every supported level near each candidate using both the full template and an independently scored central level-number region. It clicks only when both classifiers select the requested level and the nearby participant count is reliably at most 8/10; 9/10, 10/10, and unreadable counts are skipped. When neither the target nor `no_lv` is found, it rescans once before performing at most one downward scroll and one final scan. Every rescue-list refresh enforces a minimum 4.5-second interval from the actual refresh click to the next automation input; recognition and processing time count toward that interval. All supported level groups are startup-required competitors. Missing/unclickable selected levels trigger refresh-and-search instead of joining another level, while full or already-ended room popups are dismissed before rematching. After `play`, one battle-state loop checks delayed `already_end` and normal result states every 0.5 seconds for the full battle timeout; delayed ended rooms are dismissed and rematched without entering a blind result wait. Normal results and joined-battle cleanup call the shared like flow only after `tap_to_countinue` succeeds; clicking `joined_battles` does not trigger likes. `tap_to_countinue` uses foreground variants 1/2 only, confirms the page across three frames, and clicks the scaled bottom-center safe position at most twice. The battle-state loop does not accept `back` before the first confirmed Tap click. After a like-list scroll, the pointer moves away, the page settles for one second, and like recognition retries for three seconds while preserving the nine-like cap. Initial navigation and scrolling use scaled 2K-baseline coordinates.
- `src/workers/crystalis.py` - Crystalis flow. It first performs a scaled 2K-baseline wake-up click at `(2000,1000)`, then loops `click_play -> wait_win -> click_retry_or_recover_lp`. `result` matching is restricted to the right half of the game client; its committed per-image thresholds are currently set to 0.85, preventing stable matches against unrelated left-side graphics.
- `src/click/click_action.py` - collects contiguous numbered templates. Normal group actions compare the complete group against one shared frame and use only the highest-scoring candidate. Each normal template-position click samples at 0/300/600 ms; every winner must exceed its own threshold and remain near the first center, and the click uses the median center. Fixed-position page actions instead confirm presence three times, optionally restrict detection to foreground variants, then click a configured scaled 2K-baseline coordinate. Batched next-step checks share one frame across groups. Competitive level matching may inspect multiple selected-level positions in score order so crowded or unreadable rooms can be skipped. Threshold resolution reuses the worker's locked `expected_pack`. Raw/scaled click, move, and drag actions use client coordinates and detect the active pack scale tolerantly.
- `src/click/click_behavior.py` - window lookup/focus, client-only screenshot and optional normalized search-region cropping, shared-frame OpenCV matching, client-only motion sampling, participant-count analysis, and mouse action. Window borders and the title bar are never included in template matching. Normal matching applies the same 3x3 Gaussian blur to screenshot and templates before `TM_SQDIFF_NORMED`. Foreground-text matching instead uses locally adaptive screenshot binarization, an Otsu template mask, the same 7x7 outline blur on both sides, and a weighted three-pixel negative-space support region to tolerate resolution rasterization without matching plain bright areas. Template images, normal preprocessing, and foreground masks are cached by resolved path and file metadata; grouped checks reuse one capture. Mouse clicks record a monotonic timestamp, and worker-scheduled input deadlines are checked immediately before subsequent mouse input so intervening recognition time is included. Recovery positions are stored relative to the client and rebased when the window moves; a client-size change invalidates the saved position. The game must remain visible and unobstructed.
- `src/click/template_confidence.py` - parses and hot-reloads `resource/template_confidence.txt`. Every winning PNG uses its own strict threshold; Link Raid full-image and level-number winners are checked independently. Missing, duplicate, malformed, or out-of-range entries reject recognition instead of falling back to a global threshold. Before automation starts, `_start_worker()` validates that every PNG in the active pack resolves to a threshold.
- `src/packs/language_switcher.py` - `aim/` junction, pack scanning/selection, labels, `active.json`, complete PNG validation, and required-template validation. Complete validation uses Pillow in addition to the standard library.
- `src/packs/image_scaler.py` - derives 720p/1080p/4K packs from each 2560x1440 source using ImageMagick Triangle filtering. Recipe version 2 invalidates older derived output. Skip requires matching source SHA-256, recipe/tool fingerprint, and target SHA-256. Cleanup removes only files managed by a valid old manifest.
- `src/packs/file_lock.py` - repository-specific `Global\\` Windows mutex shared by switching, scaling, worker runtime leases, update-lock recovery, and the installer.
- `src/update/update_check.py` - prerelease-aware update checking and frozen-app updating. Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use `_win64`. Automatic install requires GitHub SHA-256, cancellable size/hash-checked download, safe bounded extraction, AMD64 PE validation, backups, hash verification, rollback/recovery markers, and startup-health handshake.
- `src/core/log_setup.py` - stdlib-only logging configuration called once at `main.py` import, before `QApplication`. When stderr exists, the console handler defaults to WARNING and `MAGIA_LOG_LEVEL` overrides it; windowed builds skip the missing console safely. Before any business import, the rotating file handler reads the persisted level from root `settings.json` (including the legacy `gui_log_level` key), defaulting to INFO, then the runtime selector updates both this handler and the GUI logging handler. Pillow inherits the selected root level, so PNG-block diagnostics remain visible at DEBUG. Worker `signal.emit` calls remain visible in the GUI as INFO and are mirrored through the `magia.runtime` logger with a GUI-deduplication marker, so INFO/DEBUG files contain the automation flow. Retention defaults to seven days, accepts 1–365, and startup automatically calls `cleanup_old_logs(retention_days)`; it removes only strictly named expired Magia logs and rotations while retaining the active log family. Every physical GUI line includes time, level, and source; runtime `print()` calls have been migrated to `logging.getLogger(__name__)`.
- `src/core/app_settings.py` - atomic persistence for automation mode, log level, and log retention in root `settings.json`.
- `src/core/automation_position.py` - validates, records, and resolves client-relative recovery coordinates independently of the game's screen position.
- `src/core/input_activity.py` - Windows `ctypes` keyboard/mouse activity monitor. Keyboard input, real mouse-button activity, or cumulative mouse travel pauses automation until five seconds of inactivity. Automation mouse operations use a guard context so PyAutoGUI movement and clicks do not count as user activity.

Flow:

```text
main.py -> src/workers -> src/click/click_action -> src/click/click_behavior -> game
src/workers/base.py -> src/core/input_activity.py -> Win32 user32
src/click/click_behavior.py -> src/core/automation_position.py
main.py -> src/packs/image_scaler
main.py -> src/update/update_check
```

## Critical conventions

- **Template-action return values are `2`/`1`, not booleans.** `2` means success/found/clicked; `1` means not found/keep trying/cancelled. `find_win()` is the exception: it returns a geometry tuple or `None`.
- **Template filenames use the `picture` argument, not `name`.** Template discovery collects `<picture>_1.png`, `<picture>_2.png`, and so on until the first missing number. All discovered variants share one screenshot; normal group actions use only the global highest-scoring candidate. Competitive level search is the explicit exception: it may return multiple selected-level positions in score order, but each position still compares all level groups before it can be accepted. `name` is only a log label. Numbering must start at `_1` and remain contiguous.
- Match thresholds come only from `resource/template_confidence.txt`; there is no global confidence fallback. Keys are logical PNG paths, with optional `<LANG>/...` and `<LANG>/<WxH>/...` overrides. Comparisons are strictly `score > configured_threshold`; equality is not a match. The file hot-reloads after save. Crystalis `result` entries are currently set to 0.85 and use the client area's right half.
- Normal template-position clicks require three accepted samples at 0/300/600 ms, and every sample compares the complete template group. Every winning image must pass its own threshold and every center must stay within `max(6px, client_short_side*0.8%)` of the first center; confirmation moves no mouse and the final click uses the median center. Find-only checks, raw coordinate actions, and last-safe-position recovery clicks do not use this positional filter.
- `click_fixed_position_for_item_with_result()` is a separate page-gated action: it requires three accepted presence samples at 0/300/600 ms, may restrict recognition to declared foreground variants, and then clicks the configured scaled coordinate rather than a detected center. When `_click_until()` uses this action, keep its finite click limit, never fall back to the last automation position, and do not accept a next-step template before the first confirmed page click.
- Participant-count detection is tri-state: `True` means 9/10 or 10/10, `False` means reliably at most 8/10, and `None` means unreadable. Link Raid may join only the `False` case; both crowded and unreadable candidates are skipped.
- All new PyAutoGUI input paths must wait for `_wait_for_user_idle()`, wrap bot mouse movement in `_automation_input()`, and update the last automation position after success.
- Last automation positions are client-relative records. Window movement rebases them; a client-size change or out-of-client coordinate invalidates them instead of risking a stale recovery click.
- **Run/stop state is per worker.** `_running()` is `_active and not _stop_event.is_set()`. Use `worker.stop()`; do not reintroduce global `guaji` flags.
- **LP recovery values are drinks + 1.** The GUI displays 0-10 for Link Raid and 0-8 for Crystalis, but passes `shown + 1`. Internal `1` means zero drinks and stop on first depletion.
- GUI parameters are registry-driven. There are no module-level parameter globals.

## Template packs and `aim`

- `aim/` is a runtime Windows directory junction, not a real template folder. It points to `language/<LANG>/<LANG>_<WxH>/`.
- Source packs are `language/EN/EN_2560x1440` and `language/JP/JP_2560x1440`. Derived 720p/1080p/4K directories are preserved by committed `.gitkeep` files and populated by the automatic startup refresh or `刷新列表`.
- The GUI exposes only the language dropdown. Language selection is persisted immediately on `QComboBox.activated`, even when the game is unavailable; startup restores that preference, reports when the game is not running, and selects the closest usable resolution when it is running. Programmatic refresh does not trigger language switching.
- A pack is usable only when its safe real directory tree contains at least one non-reparse PNG that passes structure, CRC, and Pillow decode checks.
- `language/active.json` stores the preferred language and last compatible resolution. The actual `aim` target remains authoritative for the template currently in use.
- `resource/template_confidence.txt` must contain a valid threshold for every logical PNG. Add the configuration entry together with a new template; never introduce a code-level default threshold.
- Never manually merge/rename `aim/` or edit derived templates as the source of truth. Add variants to the 2K source pack and regenerate.
- Do not delete empty-pack `.gitkeep` placeholders. Missing pack directories are not recreated by the scaler.

## Runtime prerequisites

- The game should use one of the supported nominal 16:9 windowed resolutions and the selected language. Startup compares client width/height independently using `max(40px, expected*10%)`, selects the closest usable pack, and then verifies it; this blocks obvious mismatch but is not pixel-perfect equivalence.
- The game must remain visible and unobstructed. Recognition and battle-motion recovery capture only the visible game client area, excluding title bars and borders. The bot repeatedly restores/activates `MadokaExedra` and uses the global mouse.
- Unknown/mismatched resolution blocks startup. Scaled coordinate actions reject an unknown pack factor rather than guessing 2K.
- `resource/main.ico` and `resource/template_confidence.txt` must remain beside the source/exe root.
- Changing the hardcoded game title requires updating `main.py`, `click_action.py`, and `click_behavior.py`, or centralizing it first.

## Bot modes

Two selectable mode flows have required starting screens. Their code is independent, but only one worker can run in one GUI process; automation, scaling, and update installation are mutually exclusive.

- **Link Raid:** start on the main/Lighthouse screen. Initial clicks use scaled 2K baselines `(2000,1000)` and `(2400,1200)`. Level choices are LV4 and LV6-LV12; all supported level templates are validated because they compete at each selected-level candidate position. It joins only candidates whose participant count is reliably at most 8/10, dismisses full/already-ended rooms, and rematches without falling back to another level. Result continuation uses foreground variants 1/2 to gate at most two bottom-center safe clicks; likes may scroll and retry for three seconds but remain capped at nine.
- **Crystalis:** start on the team-select screen where clicking `play` starts battle. A scaled `(2000,1000)` wake-up click occurs before template actions.

## Git and local artifacts

- `.gitignore` ignores `aim/`, `language/active.json`, root `settings.json`, `__pycache__/`, `*.pyc`, and `logs/`.
- `.gitignore` also ignores generated derived PNGs, `.source_hashes.json`, `.release-venv-*/`, `build/`, `dist/`, and generated `*.spec` files, while committed `.gitkeep` pack placeholders remain tracked.
- `tools/ImageMagick/` is committed and required by release packages.
- The repository has `main`, `beta`, and potentially other target branches. Never infer target branch or release channel from the current branch alone. Direct push versus PR depends on the user's request and permissions.
- Commit messages are plain-language Chinese with a concise subject and body.

## Push and release workflow

- Before every user-requested push, ask one short confirmation unless already answered: is this only a commit/push with no release, or a Release? For a Release, also confirm exact version, stable/beta channel, and target branch. A no-release push does not require a stable/beta choice.
- A no-release push must not create a tag, artifact, or GitHub Release.
- Release versions use explicit three-part SemVer. `VERSION` has no `v`; the Git tag and Release `tag_name` are exactly `v{VERSION}`, while the GitHub Release display name/title is exactly `{VERSION}` without `v`. Stable has no prerelease suffix and `prerelease=false`; beta uses the confirmed suffix and `prerelease=true`. VERSION, tag/`tag_name`, Release display name, and asset tag fragment must agree after applying their required prefixes.
- Fetch remote branches/tags first and check for an existing same-name tag, Release display name, or asset. Never move a published tag.
- Choose and record an ancestor release baseline. Stable normally uses the previous stable ancestor; beta uses the previous beta ancestor, or nearest stable ancestor if no prior beta exists. Review every commit and the full diff from baseline to release commit.
- Update `src/update/update_check.py::VERSION` and version-specific docs, including the version in the static Release badge URL and alt text in all three README files, then run all applicable non-game checks. Keep that badge on the static `img.shields.io/badge/Release-...` endpoint; do not use the dynamic `github/v/release` endpoint because GitHub Camo may cache a broken upstream response.
- Build into fresh output/staging with `pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py`; do not reuse old generated `*.spec` files or `dist/` accidentally.
- Assemble by allowlist: new `Magia_Exedra_auto.exe` and `_internal/`, plus version-controlled runtime files under `resource/`, `language/`, and `tools/`. `Magia_Exedra_auto.exe` must be at ZIP root. Exclude `aim/`, `active.json`, `.source_hashes.json`, locally generated derived PNGs, caches, Git/build metadata, and unrelated untracked files.
- New asset names are strict:
  - Stable: `MagiaExedra_auto_v<version>_win64.zip`
  - Beta: `MagiaExedra_auto_v<version-with-prerelease>_win64.zip`
- Verify ZIP CRC/entries, tracked pack placeholders, no runtime/generated files, and AMD64 PE. Run current `extract_update()` against the final ZIP and confirm its root/manifest. Confirm `find_asset()` uniquely identifies expected metadata.
- Smoke-start `Magia_Exedra_auto.exe` from a disposable copy of the final staging tree. Confirm it does not immediately exit and can create the Qt app/load workers. Remove smoke-created `aim/` and `active.json` before final ZIP. If smoke start cannot run, state why in Release notes.
- Push the intended branch first. Create a **draft Release** whose `tag_name` is `v{VERSION}` and whose display name/title is `{VERSION}` without `v`, upload the one final ZIP, wait for `state=uploaded` and GitHub digest, then compare asset name, byte size, and SHA-256 with local values. Prefer re-downloading and rechecking before publication.
- Publish only after all checks pass. The tag/Release must point to the exact pushed commit. Beta must be prerelease and never latest. On failure keep it draft or remove the bad asset/Release; never silently replace content under a published tag.
- Every Release description uses these sections in order:

  ```markdown
  ## 主要更新

  - 面向用户的改动、重要安全修复和行为变化

  ## 构建信息

  - 版本、Git tag 和目标分支
  - Windows 架构、Python 版本和 PyInstaller 版本
  - 资产文件名、字节数和 SHA-256

  ## 测试说明

  - 实际执行的检查及结果
  - （仅 beta）未完成全流程测试的范围与残余限制
  ```

- Release notes must be specific to the confirmed baseline-to-release range and kept concise (match the v2.2.0-beta style: short bullet per change; build info as one line of environment plus SHA-256; testing section as one paragraph). Only beta Releases include incomplete-full-flow-testing notes in the testing section; stable Releases do not carry such notes and list only the checks actually performed.
- After publishing, report branch, full commit hash, tag, stable/prerelease state, Release URL, asset name/size/SHA-256, checks run, residual limitations, and untracked local build artifacts.

## README and translations

- `README.md` is the Chinese source of truth. Edit it first, then mirror content into `README_EN.md` and `README_JP.md`.
- Keep the opening centered block pure HTML: `<h1>`, `<p>`, `<img>`, and `<a>`. Do not use Markdown headings/links inside it.
- Keep this language switcher identical in all three files:

  ```html
  <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  ```

- Do not translate usernames, contributor names, game-mode proper nouns, library names, code identifiers, or exact GUI labels. EN/JP may add a translated gloss after the original GUI text.
- Translate surrounding prose naturally. `README_EN.md` and `README_JP.md` must end with an AI-translation disclaimer pointing to Chinese `README.md`; Chinese README has no translation disclaimer.

## Wiki

- `wiki-draft/` is the local source of truth for the GitHub Wiki. Each `.md` filename (without extension) becomes a wiki page name; Chinese filenames are supported.
- Changes under `wiki-draft/` may be made and kept locally without immediately syncing the GitHub Wiki. When the user requests a code/version push, include any pending wiki-draft changes in the same delivery by syncing them to `https://github.com/LUODIAN-233/Magia_Exedra_auto.wiki.git` (a separate git repo on `master`). Clone it to a temp dir, copy all `wiki-draft/*.md` over, commit, and push.
- Wiki pages must mirror the corresponding `wiki-draft/*.md` exactly; do not edit wiki pages directly on GitHub.
- Preserve any wiki-only control files (e.g. `_Sidebar.md`, `_Footer.md`, `_Header.md`) that are not in `wiki-draft/`; only add or overwrite the page files that exist under `wiki-draft/`.
- The three-language cross-links inside wiki pages use relative links like `./首页`, `./Home_EN`, `./ホーム`; keep them consistent across edits.
