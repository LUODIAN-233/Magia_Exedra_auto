# AGENTS.md

Windows-only game-automation bot for **Magia Exedra** (game window title `MadokaExedra`). Image-recognition clicking (OpenCV `TM_SQDIFF_NORMED` + PyAutoGUI) with a PySide6 GUI. All code comments, README, and UI text are in Chinese.

## Running / building

- Run: `python main.py` (launches the Qt window; `if __name__ == '__main__'` sets `os.chdir` to the script/exe dir so all `./aim/...`, `./resource/...` and `./screenshot/...` paths resolve). On startup `mywindow.__init__` and the switcher's `_refresh()` call `language_switcher.ensure_active()`, which auto-creates the `aim/` junction if it is missing/broken.
- Build exe: `pyinstaller -D -i resource/main.ico main.py` (documented inline in `main.py:24`). When frozen, `OPENCV_SKIP_PYTHON_LOADER=1` is set (line 29) and `sys._MEIPASS`/`sys.executable` determine the base path; `get_executable_directory()` / `image_scaler.base_dir()` / `language_switcher.base_dir()` all share the same frozen-vs-script logic.
- **No `requirements.txt`** — install manually: `pyautogui`, `PySide6`, `opencv-python` (`cv2`), `pywinctl`. (`image_scaler.py` shells out to the committed `tools/ImageMagick/magick.exe`, so no Python imaging lib is needed.)
- **No tests, lint, typecheck, or CI.** Verify by running the bot against the live game.

## Architecture (5 files, no packages)

- `main.py` (~1100 lines) — entry point. `mywindow(QWidget)` (Qt GUI, title `圆哆啦挂机器`, icon `./resource/main.ico`, `resize(250,740)`) + two `QThread` workers + a `stop_any(QThread)`. `LanguageSwitcherWidget(QWidget)` is the language/resolution switcher UI: dropdown labels are Chinese (英语/日语 via `LANG_LABELS`), item *data* holds the real code (`EN`/`JP`); it **auto-switches on selection** (`QComboBox.activated`) — no apply button; the only button is `刷新列表`, which re-scans packs and runs `image_scaler.scale_all()` in a background `threading.Thread`, piping progress to the log via the `switched` signal.
- `click_action.py` (~120 lines) — high-level actions. `click_item_with_result` / `find_item_with_result` iterate the numbered template group; `click_position(x,y)` and `move_a_to_b(...)` do raw window-relative coordinate clicks/drags (resolves the window origin via `click_behavior.find_win('MadokaExedra')`); `click_position_scaled(x,y)` / `move_a_to_b_scaled(...)` wrap them to auto-scale **2K-baseline** coords to the active resolution — they read `language_switcher.current_selection()` + `image_scaler.scale_factor()` and multiply by the factor (0.5/0.75/1.0/1.5), so the same 2K numbers hit the same UI at 720p/1080p/2K/4K. Depends on `click_behavior`, `language_switcher`, `image_scaler`.
- `click_behavior.py` (~126 lines) — low-level. `get_xy` screenshots to `./screenshot/123.png`, OpenCV `cv2.matchTemplate(..., cv2.TM_SQDIFF_NORMED)`, `match_rate = 1 - sqrt(min_val)` (0 = perfect match), threshold **>0.8** hardcoded in `routine`/`routine_only_find`. `click_auto` does move-then-click (a raw click is rejected by the game). `find_win` focuses the game window via `pywinctl.getWindowsWithTitle('MadokaExedra')`.
- `language_switcher.py` (~257 lines) — pure-stdlib (no Qt) module managing the `aim/` junction: `list_packs()`, `current_selection()`, `switch(lang,res)`, `ensure_active()`, `pack_usable()`. Reads/writes `language/active.json` (`{lang, res}`). Runnable standalone for debugging.
- `image_scaler.py` (~213 lines) — pure-stdlib (no Qt) module that scales the `*_2560x1440` source pack to other resolutions using `tools/ImageMagick/magick.exe`. `scale_factor(res)` returns `0.5`/`0.75`/`1.5` or `None` (0.5x→1280x720 downscale, 0.75x→1920x1080 downscale, 1.5x→3840x2160 upscale; non-16:9 or the 2K source itself skipped). `scale_all(progress_cb)` walks each language's 2K pack and writes scaled copies into the other-res packs (downscaled 720p/1080p + upscaled 4K), preserving subfolder structure; existing target files are skipped (delete a target to force regeneration). Never writes into the `*_2560x1440` source pack and never follows junctions/reparse points. Runnable standalone for debugging.

Flow: `main.py` workers → `click_action` (template iteration + coords) → `click_behavior` (match + click + window). Separately, `main.py` 刷新列表 → `image_scaler.scale_all` (regenerate derived packs from 2K).

## Conventions you will get wrong without this file

- **Return values are `2`/`1`, NOT booleans.** Throughout `click_action.py`, `click_behavior.py`, `main.py` workers: `2` = success / found / clicked; `1` = not found / keep trying. `find_win` returns `(left, top)` on success but returns the int `2` if no window matches (a latent quirk — callers assume a tuple).
- **Run flags are `2`/`1` (and `3` = idle):** `guaji_1` (link raid) and `guaji_2` (crystalis) are module globals. Initial value `3` (not yet started); worker sets itself to `1` = running; `stop_any` sets `2` = stop. Worker loops run while the flag == `1`.
- **Template numbering — filename uses the *path* arg, not the *name* arg.** `click_item_with_result(self, picture, name)` / `find_item_with_result(self, picture, name)` try `<picture>_1.png`, `<picture>_2.png`, … incrementing until a file does **not** exist, trying each in turn. To add a fallback variant, drop in `<picture>_<next>.png` (where `<picture>` is the exact string passed as the first arg, e.g. `./aim/quests/link_raid/backup_requests/refresh_1.png`); the count is auto-discovered. The `name` arg is **only a log label** and never affects the filename. Match threshold `0.8` is hardcoded in `click_behavior.py` (`routine` / `routine_only_find`).
- **GUI → worker via globals, no locking.** `guaji_1`, `guaji_2` are mutated by `stop_any` and read inside worker `QThread`s. `link_raid_lv_choice` (default `6`, range lv6–lv12), `link_raid_lp_recover_times`, `crystalis_lp_recover_times` are set from the GUI and read by workers via `global`.
- **LP-recover values are "drinks + 1".** The GUI shows the *drink count* (link raid 0–10, crystalis 0–8), but the stored global is `shown + 1` (e.g. default `link_raid_lp_recover_times=1` = 0 drinks; default `crystalis_lp_recover_times=9` = 8 drinks). The worker decrements it once per depletion and stops when it hits `0`. So `1` means "stop on first depletion", not "one drink".

## Template packs & the `aim` junction

- `aim/` at the repo/exe root is a **Windows directory junction** (reparse point), NOT a real folder. It points to one of the real packs under `language/`. All runtime paths use `./aim/...` and are transparently resolved through the junction.
- Real packs live at `language/<LANG>/<LANG>_<WxH>/` (e.g. `language/EN/EN_2560x1440`). The junction target is always one of these; pack folders are never moved or renamed.
- Both source packs are populated: `language/EN/EN_2560x1440` and `language/JP/JP_2560x1440` each contain the full EN/JP template tree (`crystalis/` + `quests/link_raid/...`). The derived packs (`*_1280x720`, `*_1920x1080`, `*_3840x2160`) start **empty** (`.gitkeep` only) and are filled by 刷新列表 (downscaled from 2K, except 4K which is upscaled).
- Switching language/resolution is done **in the GUI** (`LanguageSwitcherWidget` → `language_switcher.switch(lang,res)`): selecting in the dropdown **auto-switches** — no apply button, only 刷新列表. Auto-switch fires on `QComboBox.activated` (user picks from the popup; programmatic `setCurrentIndex` during refresh is blocked with `blockSignals`, so repopulation never triggers a switch). It deletes the `aim` junction (`os.rmdir`, link-only) and recreates it with `cmd /c mklink /J` — no admin privileges. A pack is only switchable if it contains ≥1 `.png` (`pack_usable`); empty packs show as `（空）` and the switch is rejected.
- The language dropdown shows Chinese names via `LanguageSwitcherWidget.LANG_LABELS` (`EN`→英语, `JP`→日语); item *data* holds the real code. **Adding a new language requires adding its Chinese label to `LANG_LABELS`**, otherwise the bare code shows.
- `language/active.json` records `{lang, res}`. On startup `ensure_active()` restores `aim`: valid junction → keep; missing/broken → try `active.json`, else the first usable pack by scan order.
- **Do NOT** manually rename/move `aim/` or merge pack contents — it is a managed junction. To add a template variant, edit the `*_2560x1440` source pack; other-res packs are *derived* by `image_scaler.py` on 刷新列表. To force a stale derived file to regenerate, delete it. The 1.5x `*_3840x2160` pack is the only *upscaled* (non-integer) pack and is slightly less stable; the 0.5x `*_1280x720` and 0.75x `*_1920x1080` packs are *downscaled* and clean.

## Empty pack directories are placeholders — do NOT delete the `.gitkeep` files

- `language_switcher.switch()` and `image_scaler.scale_pack()` **do NOT create missing pack directories**. `switch()` requires `os.path.isdir(target)` (returns False if the pack dir is absent); `scale_pack()` iterates `os.listdir(lang_dir)` and only processes **existing** subdirs (`_run_magick`'s `os.makedirs` only fires when writing a file inside a dir already in the loop).
- Therefore every empty resolution pack (`*_1280x720`, `*_1920x1080`, `*_3840x2160`) is kept alive by a committed **`.gitkeep`** so git preserves the directory. Without them, a fresh clone has no derived-pack dirs → the GUI dropdown omits those resolutions and `image_scaler` can't populate them.
- `.gitkeep` is not a `.png`, so `pack_usable` still treats the dir as empty (`（空）`) until real templates (or scaled output) land — correct behavior. Don't "clean up" these files.

## Runtime prerequisites

- `screenshot/` **must exist** next to the script/exe. Every match attempt overwrites `./screenshot/123.png`; the folder is not auto-created and missing it errors immediately. It is preserved by a committed `screenshot/.gitkeep`.
- `resource/main.ico` lives at the **repo/exe root** (not inside the packs); `main.py` loads it via `./resource/main.ico`. Moving it out of the packs means `image_scaler.py` no longer touches it.
- Game window title is hardcoded as `'MadokaExedra'` in `click_action.py` / `click_behavior.py` (`find_win`). All window-relative coordinate math depends on it.
- Game must run **windowed at 16:9, at the same resolution as the selected template pack** (720p/1080p/2K/4K), with the matching template language; the game window must be foreground (the bot can be behind other windows, but the game cannot). The bot forces the game to foreground on start. The JP server can be switched to EN in-game to reuse the EN templates instead of re-capturing.

## Bot modes & start conditions

Two independent loops, each with a required starting screen (the bot cannot navigate there itself):
- **Link raid** (`WorkThread_1`): start at the game's main/quest (灯台) screen. The first navigation step (`into_link_raid`) uses **hardcoded window-relative coordinates** (`click_position_scaled(2000,1000)` then `click_position_scaled(2400,1200)` — 2K baselines), NOT image recognition. `click_action` reads the active pack's resolution via `language_switcher.current_selection()` + `image_scaler.scale_factor()` and scales these 2K baselines by the factor (0.5/0.75/1.0/1.5), so the first click works at all resolutions; the scrolling drags `move_a_to_b_scaled(...)` scale the same way. Level range lv6–lv12 (default lv6).
- **Crystalis** (`WorkThread_2`): start at the team-select screen (the "click play to enter battle" screen). Loops `click_play → wait_win (find result/retry) → click_retry_or_recover_lp`.

## Git / .gitignore

- `.gitignore` ignores: `aim/` (runtime junction), `language/active.json` (per-run config), `__pycache__/`, `*.pyc`. **Derived resolution packs are NOT gitignored**; their only committed content is `.gitkeep`, so pngs generated by `image_scaler` appear as untracked — commit or discard manually.
- `tools/ImageMagick/` is **committed to git** (runtime files only: `magick.exe`, `CORE_RL_*.dll`, VC/MFC runtime DLLs `msvcp140*`/`vcomp140`/`vcruntime140*`/`mfc140u`, `modules/coders` & `modules/filters`, config `*.xml`, `sRGB.icc`, `License.txt`). The scaler sets `MAGICK_HOME`/`MAGICK_CONFIGURE_PATH`/`MAGICK_CODER_MODULE_PATH`/`MAGICK_FILTER_MODULE_PATH`/`PATH` per-subprocess (without them it errors `CoderModulesPath` / `no decode delegate`); if `magick.exe` is absent it falls back to a `magick` on `PATH` with env untouched.
- Direct commits to `main`; PRs merged from forks. **Commit messages are plain-language Chinese** — a short descriptive subject and a plain-language body; favor everyday wording over `feat:`/`fix:` prefixes and jargon.

## README & multi-language docs

- `README.md` is the **Chinese source of truth** (the default). `README_EN.md` and `README_JP.md` are **derived translations**; when content changes, edit the Chinese one first, then mirror the change into the EN/JP copies. Never let the translations drift ahead of the Chinese original.
- The opening `<div align="center">` block (title + subtitle + badges + language switcher) is **pure HTML, not Markdown**: content inside an HTML block is not parsed as Markdown on strict CommonMark renderers, so a Markdown `# Title` renders as literal text instead of an `<h1>` (the title looks unstyled). Therefore use `<h1>` for the title, `<p>`/`<strong>` for the subtitle, `<img>` for badges, and `<a>` for the language-switcher links. **Never revert the title back to `#` or the links back to `[...](...)` Markdown syntax** — that reintroduces the bug.
- All three files carry the same language switcher, centered at the top of the `<div align="center">` block (after the title and badges):
  ```html
  <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  ```
  Keep it identical across the three files (same position, same text) and point links at `./README*.md` (repo-relative).
- **Do not translate:**
  - Usernames / contributor names (e.g. `TIAN000000`, `智谱AI`) — leave them verbatim in every language. (One-off name tweaks are exceptions, not a translation rule.)
  - Game mode proper nouns — `Link Raid`, `Crystalis` (the Chinese README calls the latter 晶花; the EN/JP copies use `Crystalis`, matching the code/template folder `crystalis`, to avoid ambiguity).
  - Library names & code identifiers — `OpenCV`, `TM_SQDIFF_NORMED`, `PyAutoGUI`, `PySide6`, `pywinctl`, `ImageMagick`, `MadokaExedra`, `GLM-5.2`, `backup_requests`, all `*.py` / `*.md` filenames, junction identifiers, etc.
  - **GUI button text** — the entire UI is Chinese (per "All ... UI text are in Chinese" above). In EN/JP copies, keep the original Chinese button label verbatim (e.g. `link raid挂机启动`, `自动刷晶花，需要在play界面启动`), optionally followed by a short gloss in the target language, so readers can find the actual button on screen.
- **Do translate** the surrounding prose. When leaving a technical term untranslated would make a sentence read awkwardly, choose the well-established target-language term deliberately (e.g. junction → ジャンクション, threshold → しきい値, template → テンプレート, match → マッチング, screenshot → スクリーンショット) rather than forcing an awkward literal copy.
- `README_EN.md` and `README_JP.md` each end with an **AI-translation disclaimer** (in their own language) stating the page is AI-translated, may contain ambiguities/inaccuracies, and that the Chinese `README.md` is authoritative. The Chinese `README.md` has **no** such disclaimer (it is the source).
