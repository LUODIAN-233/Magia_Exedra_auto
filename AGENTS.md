# AGENTS.md

Windows-only game-automation bot for **Magia Exedra** (game window title `MadokaExedra`). Image-recognition clicking uses OpenCV `TM_SQDIFF_NORMED` plus PyAutoGUI, with a PySide6 GUI. Code comments and GUI prose are Chinese-first. `README.md` is authoritative; `README_EN.md` and `README_JP.md` are maintained translations.

## Running / building

- Run: `python main.py`. The entry point changes cwd to the script/exe directory so relative runtime paths resolve. Startup calls `language_switcher.ensure_active()`, which restores or creates the `aim/` junction.
- Build: `pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py`. `--windowed` prevents an empty console window from opening beside the GUI. The built entry is named `Magia_Exedra_auto.exe` via `-n`; this is the executable shipped in releases. This creates only the PyInstaller onedir output; a distributable package must also place `resource/`, `language/`, and `tools/` beside `Magia_Exedra_auto.exe`.
- In frozen mode, `OPENCV_SKIP_PYTHON_LOADER=1` must be set before anything imports `cv2`.
- **DPI-sensitive import order:** keep `src.workers` lazy. Startup must remain `QApplication(...) -> mywindow() -> get_worker_registry()`. Importing workers earlier imports PyAutoGUI and may prevent Qt from setting Windows DPI awareness. `main.py` calls `log_setup.configure_logging()` at module import, before `QApplication`; this is stdlib-only and safe, and must stay before any business module import so all loggers are captured.
- Runtime dependencies are declared in `requirements.txt` (`pyautogui`, `PySide6`, `opencv-python`, `numpy`, `pywinctl`, `Pillow`); install with `pip install -r requirements.txt`. Building additionally requires `pyinstaller` (listed but commented out in `requirements.txt`). Scaling uses committed `tools/ImageMagick/magick.exe` or `magick` on PATH.
- There is no formal test suite, lint/typecheck config, or CI. Still run every applicable non-game check: Python compile/import checks, worker registry and template validation, update ZIP/extraction checks, lock/updater checks, AMD64 PE validation, and packaged-app smoke start.

## Architecture

Mode-specific automation lives in `src/workers/`. `main.py` is the GUI entry and application-level task controller: it constructs workers, injects parameters, coordinates automation/scaling/update mutual exclusion, performs startup checks, orchestrates updates, and handles cooperative shutdown. It does not contain Link Raid or Crystalis flow logic.

- `main.py` - `mywindow(QWidget)` plus `LanguageSwitcherWidget`. It lazily builds one worker and parameter page per `WorkerMeta`; no worker class is hardcoded in the GUI. `_start_worker()` rejects concurrent tasks, unresolved update-recovery markers, missing game windows, unknown/mismatched client resolution, incomplete required template groups, and invalid parameters. It reads parameters before expanding dynamic required-template paths. Resolution mismatch is a hard block. A GUI logging handler has a runtime-selectable DEBUG/INFO/WARNING/ERROR/CRITICAL threshold; worker user messages are unaffected. Frozen console-mode compatibility hides an existing console, while new builds use `--windowed`. `closeEvent()` uses one shared 12-second deadline to stop/wait for workers, scaling, update checks, and update preparation. Update signals include a task ID so stale thread results are ignored. Source-mode automatic checks log the Release URL; only manual checks open it.
- `src/workers/registry.py` - `ParamSpec` describes GUI parameters. `WorkerMeta` contains `name`, `label`, `worker_class`, `params`, `start_hint`, and `required_templates`. Required template paths are relative to the pack root, omit `_<number>.png`, and may contain placeholders such as `{level_choice}` referencing declared `ParamSpec.key` values. They cover startup-critical groups; optional best-effort groups need not block startup. Adding a mode requires a no-argument-constructible `BaseWorker` subclass decorated with `@register`, plus an import in `src/workers/__init__.py`.
- `src/workers/base.py` - `BaseWorker(QThread)`, `retry_until()`, `RETRY_TIMEOUT=60`, and `BATTLE_TIMEOUT=1800`. Per-worker state is `_active` plus `_stop_event`; `start()` refuses restart while the old thread still runs. Each run starts a `UserActivityGuard`, tracks the last automation position, and pauses template actions while the user is active. During a click-template wait, every 5-second miss observes the game client for 2 seconds: more than 50% changed pixels skips only that recovery cycle as likely battle animation; otherwise one recovery click uses the last safe automation position. After a recovery click, `_click_until()` first checks explicitly declared next-step templates; if none is present, it redundantly checks and clicks the current template. The 5-second cycle continues until success, timeout, or cancellation. `_run_safely()` holds the cross-process template mutex for the full worker run, rechecks `expected_pack`, handles cancellation/lock timeout/errors, and always calls `_finish()` in `finally`. Concrete workers must route `run()` through `_run_safely()`.
- `src/workers/link_raid.py` - Link Raid flow: navigation, backup requests, refresh, joined-battle cleanup, level selection, join/LP handling, battle completion, likes, and return. Normal results and joined-battle cleanup call the shared like flow only after `tap_to_countinue` succeeds; clicking `joined_battles` does not trigger likes. Initial navigation and scrolling use scaled 2K-baseline coordinates. If the selected level is unavailable or cannot be clicked, it refreshes and searches again instead of joining another level.
- `src/workers/crystalis.py` - Crystalis flow. It first performs a scaled 2K-baseline wake-up click at `(2000,1000)`, then loops `click_play -> wait_win -> click_retry_or_recover_lp`.
- `src/click/click_action.py` - collects contiguous numbered templates, compares the full group against one shared frame, chooses only the highest-scoring candidate, performs raw/scaled coordinate actions, and detects client resolution tolerantly.
- `src/click/click_behavior.py` - window lookup/focus, visible game-window screenshot, shared-frame OpenCV matching, client-only motion sampling, and mouse action. Matching applies the same 3x3 Gaussian blur to screenshot and templates before `TM_SQDIFF_NORMED`. The game must remain visible and unobstructed.
- `src/packs/language_switcher.py` - `aim/` junction, pack scanning/selection, labels, `active.json`, complete PNG validation, and required-template validation. Complete validation uses Pillow in addition to the standard library.
- `src/packs/image_scaler.py` - derives 720p/1080p/4K packs from each 2560x1440 source using ImageMagick Triangle filtering. Recipe version 2 invalidates older derived output. Skip requires matching source SHA-256, recipe/tool fingerprint, and target SHA-256. Cleanup removes only files managed by a valid old manifest.
- `src/packs/file_lock.py` - repository-specific `Global\\` Windows mutex shared by switching, scaling, worker runtime leases, update-lock recovery, and the installer.
- `src/update_check.py` - prerelease-aware update checking and frozen-app updating. Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use `_win64`. Automatic install requires GitHub SHA-256, cancellable size/hash-checked download, safe bounded extraction, AMD64 PE validation, backups, hash verification, rollback/recovery markers, and startup-health handshake.
- `src/log_setup.py` - stdlib-only logging configuration called once at `main.py` import, before `QApplication`. When stderr exists, the console handler defaults to WARNING and `MAGIA_LOG_LEVEL` overrides it; windowed builds skip the missing console safely. A rotating DEBUG file handler writes to `logs/`. `main.py` adds a GUI logging handler defaulting to WARNING with a runtime level selector. Worker `signal.emit` calls remain the unfiltered user-facing GUI log channel and are not replaced by `logging`; runtime `print()` calls have been migrated to `logging.getLogger(__name__)`.
- `src/input_activity.py` - Windows `ctypes` keyboard/mouse activity monitor. Keyboard input or cumulative large mouse movement pauses automation until five seconds of inactivity. Automation mouse operations use a guard context so PyAutoGUI movement does not count as user activity.

Flow:

```text
main.py -> src/workers -> src/click/click_action -> src/click/click_behavior -> game
src/workers/base.py -> src/input_activity.py -> Win32 user32
main.py -> src/packs/image_scaler
main.py -> src/update_check
```

## Critical conventions

- **Template-action return values are `2`/`1`, not booleans.** `2` means success/found/clicked; `1` means not found/keep trying/cancelled. `find_win()` is the exception: it returns a geometry tuple or `None`.
- **Template filenames use the `picture` argument, not `name`.** Template discovery collects `<picture>_1.png`, `<picture>_2.png`, and so on until the first missing number. All discovered variants share one screenshot; only the global highest-scoring candidate can be clicked/found. `name` is only a log label. Numbering must start at `_1` and remain contiguous.
- Match threshold is strictly `> 0.8` via `MATCH_THRESHOLD`; a score equal to 0.8 is not a match.
- All new PyAutoGUI input paths must wait for `_wait_for_user_idle()`, wrap bot mouse movement in `_automation_input()`, and update the last automation position after success.
- **Run/stop state is per worker.** `_running()` is `_active and not _stop_event.is_set()`. Use `worker.stop()`; do not reintroduce global `guaji` flags.
- **LP recovery values are drinks + 1.** The GUI displays 0-10 for Link Raid and 0-8 for Crystalis, but passes `shown + 1`. Internal `1` means zero drinks and stop on first depletion.
- GUI parameters are registry-driven. There are no module-level parameter globals.

## Template packs and `aim`

- `aim/` is a runtime Windows directory junction, not a real template folder. It points to `language/<LANG>/<LANG>_<WxH>/`.
- Source packs are `language/EN/EN_2560x1440` and `language/JP/JP_2560x1440`. Derived 720p/1080p/4K directories are preserved by committed `.gitkeep` files and populated by `刷新列表`.
- Dropdown selection auto-switches on `QComboBox.activated`; programmatic refresh does not trigger switching. Empty/invalid packs show `（空）`.
- A pack is usable only when its safe real directory tree contains at least one non-reparse PNG that passes structure, CRC, and Pillow decode checks.
- `language/active.json` stores the last selection. The actual `aim` target remains authoritative.
- Never manually merge/rename `aim/` or edit derived templates as the source of truth. Add variants to the 2K source pack and regenerate.
- Do not delete empty-pack `.gitkeep` placeholders. Missing pack directories are not recreated by the scaler.

## Runtime prerequisites

- The game should use the selected pack's nominal 16:9 windowed resolution and language. Startup compares client width/height independently using `max(40px, expected*10%)`; this blocks obvious mismatch but is not pixel-perfect equivalence.
- The game must remain visible and unobstructed. Recognition captures the visible game-window region, while battle-motion recovery samples only the game client area. The bot repeatedly restores/activates `MadokaExedra` and uses the global mouse.
- Unknown/mismatched resolution blocks startup. Scaled coordinate actions reject an unknown pack factor rather than guessing 2K.
- `resource/main.ico` must remain beside the source/exe root.
- Changing the hardcoded game title requires updating `main.py`, `click_action.py`, and `click_behavior.py`, or centralizing it first.

## Bot modes

Two selectable mode flows have required starting screens. Their code is independent, but only one worker can run in one GUI process; automation, scaling, and update installation are mutually exclusive.

- **Link Raid:** start on the main/Lighthouse screen. Initial clicks use scaled 2K baselines `(2000,1000)` and `(2400,1200)`. Level choices are LV4 and LV6-LV12; the selected level template is validated dynamically. Missing/unclickable selected levels trigger refresh-and-search, never fallback joining another level.
- **Crystalis:** start on the team-select screen where clicking `play` starts battle. A scaled `(2000,1000)` wake-up click occurs before template actions.

## Git and local artifacts

- `.gitignore` ignores `aim/`, `language/active.json`, `__pycache__/`, `*.pyc`, and `logs/`.
- Derived PNGs, `.source_hashes.json`, `build/`, `dist/`, and generated `main.spec` may appear untracked. Never stage them accidentally.
- `tools/ImageMagick/` is committed and required by release packages.
- The repository has `main`, `beta`, and potentially other target branches. Never infer target branch or release channel from the current branch alone. Direct push versus PR depends on the user's request and permissions.
- Commit messages are plain-language Chinese with a concise subject and body.

## Push and release workflow

- Before every user-requested push, ask one short confirmation unless already answered: is this only a commit/push with no release, or a Release? For a Release, also confirm exact version, stable/beta channel, and target branch. A no-release push does not require a stable/beta choice.
- A no-release push must not create a tag, artifact, or GitHub Release.
- Release versions use explicit three-part SemVer. `VERSION` has no `v`; the tag is exactly `v{VERSION}`. Stable has no prerelease suffix and `prerelease=false`; beta uses the confirmed suffix and `prerelease=true`. VERSION, tag, Release `tag_name`, and asset tag fragment must agree.
- Fetch remote branches/tags first and check for an existing same-name tag, Release, or asset. Never move a published tag.
- Choose and record an ancestor release baseline. Stable normally uses the previous stable ancestor; beta uses the previous beta ancestor, or nearest stable ancestor if no prior beta exists. Review every commit and the full diff from baseline to release commit.
- Update `src/update_check.py::VERSION` and version-specific docs, then run all applicable non-game checks.
- Build into fresh output/staging with `pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py`; do not reuse old untracked `main.spec` or `dist/` accidentally.
- Assemble by allowlist: new `Magia_Exedra_auto.exe` and `_internal/`, plus version-controlled runtime files under `resource/`, `language/`, and `tools/`. `Magia_Exedra_auto.exe` must be at ZIP root. Exclude `aim/`, `active.json`, `.source_hashes.json`, locally generated derived PNGs, caches, Git/build metadata, and unrelated untracked files.
- New asset names are strict:
  - Stable: `MagiaExedra_auto_v<version>_win64.zip`
  - Beta: `MagiaExedra_auto_v<version-with-prerelease>_win64.zip`
- Verify ZIP CRC/entries, tracked pack placeholders, no runtime/generated files, and AMD64 PE. Run current `extract_update()` against the final ZIP and confirm its root/manifest. Confirm `find_asset()` uniquely identifies expected metadata.
- Smoke-start `Magia_Exedra_auto.exe` from a disposable copy of the final staging tree. Confirm it does not immediately exit and can create the Qt app/load workers. Remove smoke-created `aim/` and `active.json` before final ZIP. If smoke start cannot run, state why in Release notes.
- Push the intended branch first. Create a **draft Release**, upload the one final ZIP, wait for `state=uploaded` and GitHub digest, then compare asset name, byte size, and SHA-256 with local values. Prefer re-downloading and rechecking before publication.
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
- When `wiki-draft/` has changes, sync them to the GitHub Wiki repository at `https://github.com/LUODIAN-233/Magia_Exedra_auto.wiki.git` (a separate git repo on `master`). Clone it to a temp dir, copy all `wiki-draft/*.md` over, commit, and push. Do this whenever wiki drafts change, independent of code releases.
- Wiki pages must mirror the corresponding `wiki-draft/*.md` exactly; do not edit wiki pages directly on GitHub.
- Preserve any wiki-only control files (e.g. `_Sidebar.md`, `_Footer.md`, `_Header.md`) that are not in `wiki-draft/`; only add or overwrite the page files that exist under `wiki-draft/`.
- The three-language cross-links inside wiki pages use relative links like `./首页`, `./Home_EN`, `./ホーム`; keep them consistent across edits.
