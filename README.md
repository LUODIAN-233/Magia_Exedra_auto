<div align="center">
  <h1>Magia Exedra 自动挂机</h1>
  <p>面向 Windows 的 Magia Exedra 图像识别自动化工具</p>
  <p>支持 Link Raid、晶花、英语/日语模板与多分辨率窗口</p>
  <p>
    <img alt="Platform" src="https://img.shields.io/badge/平台-Windows-0078D4">
    <img alt="Architecture" src="https://img.shields.io/badge/架构-x86--64-555555">
    <img alt="GUI" src="https://img.shields.io/badge/界面-PySide6-41CD52">
    <a href="https://github.com/LUODIAN-233/Magia_Exedra_auto/releases"><img alt="Release 2.4.3" src="https://img.shields.io/badge/Release-2.4.3-2ea44f"></a>
  </p>
  <p>
    <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  </p>
</div>

---

## 2.4.3 更新

- EXE 启动时先完成自动更新检查，再开始模板缩放；接受更新不会再被缩放任务阻止，下载取消或失败后会恢复缩放。
- Link Raid 点击 `play` 后会在整个战斗等待期持续检查延迟出现的 `already_end`。只有完整弹窗文字与对应 `OK` 在中央区域连续三帧同时命中时才单击关闭并重新匹配，单帧误报不会触发通用 `OK`。
- 等级列表初扫失败后会先复扫，再至多向下滑动一次并进行最后扫描。刷新按钮实际点击到下一次自动化输入至少间隔 4.5 秒，期间的识别和处理耗时计入间隔。

## 下载与启动

1. 前往 [GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases) 下载最新的 Windows ZIP。
2. 将 ZIP **完整解压**到一个普通文件夹。
3. 运行根目录中的 `Magia_Exedra_auto.exe`。

> [!IMPORTANT]
> 不要只复制 EXE。程序还需要同级的 `_internal/`、`resource/`、`language/` 和 `tools/`。

## 两种挂机模式

| 模式 | 开始前停留界面 | 可调参数 | 自动执行 |
|:-----|:---------------|:---------|:---------|
| **Link Raid** | 游戏主界面（灯台界面） | LV4 或 LV6-LV12、体力药次数 | 进入求援、刷新、选择指定等级、加入战斗、清理结算与点赞 |
| **晶花** | 已选好关卡和队伍，点击 `play` 即可开战 | 体力药次数 | 开始战斗、等待结算、点击 `retry` 并继续周回 |

脚本找不到目标、等待超时或体力药次数用完时会安全停止。Link Raid 不会在所选等级缺失时改加入其它等级。

## 第一次使用

1. 以窗口模式启动游戏，并让游戏画面保持完整可见。
2. 启动本工具，等待模板列表刷新完成；选择游戏语言，分辨率会按游戏客户区自动匹配。
3. 选择「挂机模式」，设置参数，然后点击「启动挂机」。

运行期间如需操作电脑，可直接使用键盘或移动鼠标；脚本会暂停，并在连续 5 秒无用户操作后继续。点击「停止挂机」可结束当前任务。

> [!NOTE]
> 如果模板状态提示未检测到游戏，请先确认游戏窗口标题为 `MadokaExedra`，且游戏已经完成启动。

## 关键设置

| 设置 | 说明 |
|:-----|:-----|
| 游戏语言 | 支持英语与日语，程序会记住最后选择 |
| 分辨率 | 自动识别并选择 `720p` / `1080p` / `2K` / `4K` 模板，无需手动选择 |
| 日志等级 | 新安装默认 `INFO`；该设置同时控制 GUI 调试记录与 `logs/` 文件 |
| 日志保留 | 默认 7 天，可设为 1-365 天；启动时自动清理，也可手动清理过时日志 |
| beta 更新 | 预发布版本默认启用 beta 更新通道，可在「设置」中调整 |

## 使用须知

- 仅支持 Windows x86-64 / AMD64 和窗口模式游戏。
- 游戏窗口必须保持可见，识图区域不能被其它窗口遮挡。
- 工具会激活游戏窗口并使用全局鼠标；启动挂机前请确认起始界面正确。
- 实际识别效果会受到游戏语言、窗口尺寸、DPI 和模板质量影响。
- 本工具仅供学习交流，请遵守游戏服务条款并自行承担使用风险。

## 遇到问题

| 现象 | 先检查 |
|:-----|:-------|
| 未检测到游戏 | 游戏是否已启动、窗口标题是否为 `MadokaExedra` |
| 模板显示「（空）」 | 等待启动刷新完成，或点击「刷新列表」重新生成模板 |
| 无法启动挂机 | 游戏语言、窗口分辨率、起始界面和必需模板是否匹配 |
| 识别异常或误点击 | 保持窗口无遮挡，将日志等级设为 `DEBUG` 后复现并查看 `logs/` |

更完整的操作说明、识别保护机制和故障排查见 [Wiki · 使用指南](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/使用指南)。

## 文档

| 内容 | 入口 |
|:-----|:-----|
| 普通用户操作与排查 | [使用指南](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/使用指南) |
| 从源码运行与构建 | [源码运行与构建](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建) |
| 模板制作与分辨率 | [模板包与分辨率](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/模板包与分辨率) |
| 架构、开发和发布 | [Wiki 首页](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki) |

## 鸣谢

| 贡献者 | 贡献内容 |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ 脚本整体思路及后续维护 |
| **洛殿** | v1.0.0+ 部分日语素材及分辨率缩放方案；v2.0.0+ 算力支撑及日语素材 |
| **智谱AI** | v2.0.0+ 由 GLM-5.2 完成重写与构建 |
