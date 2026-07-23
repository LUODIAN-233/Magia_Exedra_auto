# Automatic updates and releases

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Version numbering

- Versions use explicit three-part SemVer, e.g. `2.2.0`, `2.2.0-beta`
- `VERSION` (in `src/update_check.py`) has no `v` prefix; the tag is exactly `v{VERSION}`
- Stable has no prerelease suffix and `prerelease=false`
- Beta uses the confirmed suffix and `prerelease=true`
- VERSION, tag, Release `tag_name`, and asset tag fragment must all agree

## Update checking

`src/update_check.py` queries the GitHub Releases API for the latest release and compares it with the local `VERSION` using semantic version comparison.

- Downgrade protection: only when the remote version is strictly greater than the local version is an update reported
- When the remote is less than or equal to local, it always reports "up to date" and never suggests a downgrade
- Query failures (no network, API rate limit, parse errors) do not raise; they return `has_update=False` with a message

### Update channels

- **stable channel** (default): only looks at official releases (`releases/latest` excludes prereleases); never suggests beta
- **beta channel**: looks at all releases (including prereleases) and picks the semver-greatest, which may be a beta. Prerelease versions compare per semver (official release > same-version prerelease)

In source mode, automatic checks only log the Release URL; only manual checks open it.

## Safe installation

Automatic installation requires:

- GitHub SHA-256
- Cancellable size/hash-checked download
- Safe bounded extraction
- AMD64 PE validation
- Backups
- Hash verification
- Rollback/recovery markers
- Startup-health handshake

Reading remains compatible with one unique `MagiaExedra_auto_<tag>.zip` or `MagiaExedra_auto_<tag>_win64.zip`; new releases must use the `_win64` suffix.

## Asset naming

Asset names are strict:

- Stable: `MagiaExedra_auto_v<version>_win64.zip`
- Beta: `MagiaExedra_auto_v<version-with-prerelease>_win64.zip`

## Release workflow

1. Fetch remote branches/tags first and check for an existing same-name tag, Release, or asset. Never move a published tag
2. Choose and record an ancestor release baseline. Stable normally uses the previous stable ancestor; beta uses the previous beta ancestor, or the nearest stable ancestor if no prior beta exists
3. Review every commit and the full diff from baseline to release commit
4. Update `src/update_check.py::VERSION` and version-specific docs, then run all applicable non-game checks
5. Build into a fresh output/staging directory with `pyinstaller -D -i resource/main.ico main.py`; do not reuse old untracked `main.spec` or `dist/`
6. Assemble by allowlist: new `main.exe` and `_internal/`, plus version-controlled runtime files under `resource/`, `language/`, and `tools/`. `main.exe` must be at the ZIP root. Exclude `aim/`, `active.json`, `.source_hashes.json`, locally generated derived PNGs, caches, Git/build metadata, and unrelated untracked files
7. Verify ZIP CRC/entries, tracked pack placeholders, no runtime/generated files, and AMD64 PE. Run current `extract_update()` against the final ZIP and confirm its root/manifest. Confirm `find_asset()` uniquely identifies expected metadata
8. Smoke-start `main.exe` from a disposable copy of the final staging tree. Confirm it does not immediately exit and can create the Qt app/load workers. Remove smoke-created `aim/` and `active.json` before the final ZIP
9. Push the intended branch first. Create a **draft Release**, upload the one final ZIP, wait for `state=uploaded` and the GitHub digest, then compare asset name, byte size, and SHA-256 with local values. Prefer re-downloading and rechecking before publication
10. Publish only after all checks pass. The tag/Release must point to the exact pushed commit. Beta must be prerelease and never latest. On failure keep it draft or remove the bad asset/Release; never silently replace content under a published tag

## Release notes format

Every Release description uses these sections in order:

```markdown
## 主要更新

- User-facing changes, important security fixes, and behavioral changes

## 构建信息

- Version, Git tag, and target branch
- Windows architecture, Python version, and PyInstaller version
- Asset filename, byte size, and SHA-256

## 测试说明

- Checks actually performed and results
- (beta only) Scope and residual limitations of incomplete full-flow testing
```

Release notes must be specific to the confirmed baseline-to-release range. Only beta Releases include incomplete-full-flow-testing notes in the testing section; stable Releases do not carry such notes and list only the checks actually performed.

## Post-release report

After publishing, report: branch, full commit hash, tag, stable/prerelease state, Release URL, asset name/size/SHA-256, checks run, residual limitations, and untracked local build artifacts.

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./自动更新与发布).
