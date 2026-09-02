<div align="center">
  <h1>Magia Exedra Auto Bot</h1>
  <p>Image-recognition automation for Magia Exedra on Windows</p>
  <p>Supports Link Raid, Crystalis, English/Japanese templates, and multiple window resolutions</p>
  <p>
    <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-0078D4">
    <img alt="Architecture" src="https://img.shields.io/badge/Architecture-x86--64-555555">
    <img alt="GUI" src="https://img.shields.io/badge/GUI-PySide6-41CD52">
    <a href="https://github.com/LUODIAN-233/Magia_Exedra_auto/releases"><img alt="Release 2.5.2" src="https://img.shields.io/badge/Release-2.5.2-2ea44f"></a>
  </p>
  <p>
    <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  </p>
</div>

---

## 2.5.2 changes

- Fixed old installations retaining the removed `love_1.png`, which made template-confidence validation fail and blocked automation. Template refresh now removes that exact retired file from both source and derived packs while preserving other untracked files.

## Download and launch

1. Download the latest Windows ZIP from [GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases).
2. **Extract the entire ZIP** into a normal folder.
3. Run `Magia_Exedra_auto.exe` at the package root.

> [!IMPORTANT]
> Do not copy only the EXE. `_internal/`, `resource/`, `language/`, and `tools/` must remain beside it.

## Farming modes

| Mode | Screen before starting | Options | Automation |
|:-----|:-----------------------|:--------|:-----------|
| **Link Raid** | Main/Lighthouse screen | Multiple levels and priority, separate 9/10 and 10/10 room rules, stamina-potion count | Opens backup requests, refreshes, selects levels by priority, joins battles, and clears results |
| **Crystalis** | Stage and team selected; clicking `play` would start battle | Stamina-potion count | Starts battle, waits for results, clicks `retry`, and continues farming |

The task stops safely when a target cannot be found, a wait times out, or the configured potion count is exhausted. Link Raid can enable LV4 and LV6-LV12 together. If the highest-priority level has no eligible room, it immediately tries the next selected level and never joins an unselected level. An unreadable participant count is allowed; 9/10 and 10/10 rooms can each be skipped or attempted independently.

## First run

1. Start the game in windowed mode and keep its full image visible.
2. Launch this tool and wait for the template list to finish refreshing. Select the game language; resolution is matched automatically from the game client area.
3. Select `挂机模式` (automation mode), set its options, and click `启动挂机` (start). The selected mode and every mode's parameters are saved immediately after changes and restored on the next launch.

You may use the keyboard or move the mouse while the task is active. Automation pauses and resumes after five seconds without user input. Click `停止挂机` to end the current task.

> [!NOTE]
> If the template status says the game was not detected, verify that the game has finished launching and its window title is `MadokaExedra`.

## Essential settings

| Setting | Behavior |
|:--------|:---------|
| Game language | English and Japanese are supported; the last selection is remembered |
| Resolution | Automatically selects `720p` / `1080p` / `2K` / `4K` templates |
| Automation options | All parameters are remembered per mode; Link Raid initially selects only LV6 and skips both 9/10 and 10/10 rooms |
| Log level | New installations default to `INFO`; the setting controls GUI debug records and files under `logs/` |
| Log retention | Defaults to seven days and supports 1-365 days; cleanup runs at startup or manually |
| Beta updates | Prerelease builds enable the beta channel by default; change it under `设置` |
| Server酱 notifications | Disabled by default; configure a masked SendKey, one or two delivery channels, and major events; settings remain in local `settings.json` |

Server酱 channels include WeChat service and test accounts, WeCom application messages, WeCom/DingTalk/Feishu group bots, Bark, PushDeer, the official Android client, and a custom Webhook; select one or two channels. Delivery runs in the background, identical events are deduplicated for ten minutes, and failures are retried up to three times. Automatic script termination has its own event, while manual stop or application close sends nothing; stamina exhaustion, timeout, and abnormal termination do not also send the automatic-termination event. The SendKey is never written to logs.

For first-time setup, see the Chinese [Server酱 notification setup guide](./README_SERVERCHAN.md), including login, subscription/payment, dedicated SendKey, and fee-recipient details.

## Before use

- Only windowed Windows x86-64 / AMD64 gameplay is supported.
- Keep the game visible and do not cover recognition areas with other windows.
- The tool activates the game and uses the global mouse; verify the required starting screen first.
- Recognition can be affected by game language, window size, DPI, and template quality.
- This tool is provided for learning and communication. Follow the game's terms of service and use it at your own risk.

## Troubleshooting

| Symptom | Check first |
|:--------|:------------|
| Game not detected | The game is running and its window title is `MadokaExedra` |
| Templates show `（空）` | Wait for startup refresh, or click `刷新列表` to regenerate templates |
| Automation will not start | Game language, resolution, starting screen, and required templates match |
| Recognition error or wrong click | Keep the game unobstructed, select `DEBUG`, reproduce once, and inspect `logs/` |

See [Wiki · User guide](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/User-guide) for full workflows, recognition safeguards, and troubleshooting.

## Documentation

| Topic | Page |
|:------|:-----|
| User workflows and troubleshooting | [User guide](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/User-guide) |
| Run from source and build | [Run from source and build](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/Run-from-source-and-build) |
| Templates and resolutions | [Template packs and resolutions](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/Template-packs-and-resolutions) |
| Architecture, development, and releases | [Wiki Home](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/Home_EN) |

## Acknowledgments

| Contributor | Contribution |
|:-----------:|:-------------|
| **TIAN000000** | v1.0.0+ overall script design and ongoing maintenance |
| **洛殿** | v1.0.0+ Japanese assets and resolution-scaling approach; v2.0.0+ compute support and Japanese assets |
| **智谱AI** | v2.0.0+ rewrite and build by GLM-5.2 |

## Translation Notice

This page was translated by AI and may contain ambiguities or inaccuracies. For authoritative content, refer to the original [简体中文 README](./README.md).
