<div align="center">
  <h1>Magia Exedra 自動周回ボット</h1>
  <p>画像認識ベースの <strong>Magia Exedra</strong> Windows 向け自動化ツール</p>
  <p>Link Raid／Crystalis、英語・日本語テンプレート、複数解像度に対応</p>
  <p>
    <img alt="Platform" src="https://img.shields.io/badge/プラットフォーム-Windows-blue">
    <img alt="Python" src="https://img.shields.io/badge/Python-3.x-blue">
    <img alt="Qt" src="https://img.shields.io/badge/GUI-PySide6-green">
    <img alt="License" src="https://img.shields.io/badge/用途-ゲーム補助-orange">
  </p>
  <p>
    <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  </p>
</div>

---

## 機能

- **Link Raid：** backup requests への移動、更新、LV6-LV12 の検索、終了済み戦闘の整理、参加、いいねを自動化
- **Crystalis：** `play`、結果待ち、`retry` による周回を自動化
- 両モードで体力薬の使用回数を設定でき、回数を使い切ると停止
- 英語／日本語テンプレートと 720p / 1080p / 2K / 4K に対応
- 通常画面を60秒、戦闘を30分以内に認識できない場合は安全に停止
- 起動前にゲームウィンドウ、解像度、必須テンプレートを確認し、明らかな誤クリックを防止
- stable / beta の更新確認に対応し、リリース版は検証済み更新パッケージを安全にインストール可能

## ダウンロード

[GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases) から完全な ZIP をダウンロードして解凍し、ルートの `main.exe` を実行します。

> EXE だけをコピーしないでください。同じ階層に `_internal/`、`resource/`、`language/`、`tools/` が必要です。

## クイックスタート

### Link Raid

1. ゲームをメイン／灯台画面にします。
2. `选择挂机脚本` で `link raid挂机启动` を選択します。
3. レベルと体力薬の回数を設定します。
4. `启动：link raid挂机启动` をクリックします。

### Crystalis

1. ステージと編成を選び、`play` を押すと戦闘が始まる画面で待機します。
2. `选择挂机脚本` で `自动刷晶花，需要在play界面启动` を選択します。
3. 体力薬の回数を設定します。
4. `启动：自动刷晶花，需要在play界面启动` をクリックします。

`停下当前运行的脚本` をクリックすると、現在のタスクへ停止を要求します。

## テンプレート設定

- 言語と解像度を選択すると自動で切り替わります
- 表示される中国語ラベル `英语`、`日语` は `EN`、`JP` に対応します
- `（空）` はテンプレート pack が現在使用できないことを示します
- `刷新列表` は2K原本から 720p / 1080p / 4K テンプレートを生成します
- ゲーム言語とウィンドウ解像度を有効な pack に合わせてください

## 使用前の注意

- Windows x86-64 / AMD64 のウィンドウモードのみ対応
- ゲームを表示したままにし、認識領域を他のウィンドウで隠さないでください
- bot はゲームをアクティブ化し、グローバルマウスを使用するため、同時にマウスを操作しないでください
- 720p / 1080p / 2K / 4K の座標換算に対応しますが、認識は DPI、ウィンドウサイズ、テンプレート品質の影響を受けます
- JP サーバーはゲーム内で EN に切り替えると英語テンプレートを再利用できます
- 実ゲーム上の全モード／言語／解像度の組み合わせは未検証です。最初は短時間監視してください

## Wiki

ソース実行、ビルド、アーキテクチャ、テンプレート保守、更新セキュリティ、開発規約は中国語 Wiki に移動しました：

- [Wiki ホーム](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki)
- [ソース実行とビルド](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建)
- [アーキテクチャ](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/项目架构)
- [テンプレート pack と解像度](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/模板包与分辨率)
- [自動更新とリリース](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/自动更新与发布)
- [開発規約](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/开发约定)

## 謝辞

| 貢献者 | 貢献内容 |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ スクリプト全体の構想および継続メンテナンス |
| **洛殿** | v1.0.0+ 日本語素材の一部および解像度スケーリング手法<br>v2.0.0+ 計算リソースの提供および日本語素材 |
| **智谱AI** | v2.0.0+ GLM-5.2 による全面書き換えとビルド |

---

本スクリプトは学習・交流目的のみです。ゲームの利用規約を遵守し、利用による結果は利用者自身が負うものとします。

## 翻訳に関するお知らせ

このページは AI による翻訳であり、曖昧さや不正確な箇所が含まれる可能性があります。正確な情報は [簡体中文 README](./README.md) を参照してください。
