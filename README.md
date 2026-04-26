# ShadowAnswer

> ハックツハッカソン向けジョークアプリ。
> 実在する試験・テストでの不正行為を目的とした利用は想定していません!

## 概要

カンニング48 は、四択問題の画面キャプチャを Gemini に問い合わせ、
キーボード LED・トレイ表示・P2P 投票を使って結果を共有するアプリです。

現行版は「目立たず動き続ける」ことを重視し、例外時にクラッシュしにくい設計になっています。

## 現在の主な機能

1. AI 回答（画面キャプチャ）
    - ホットキーで画面全体を `mss` でキャプチャし、`google-genai` 経由で問い合わせ。
    - 回答は数字（1-4）または `?` に正規化。
    - 回答が有効（1-4）の場合はcapslockのLEDをこっそり光らせて通知を実行します。

2. クリップボード AI 置換
    - 選択テキストを取得して AI に送信し、返答でクリップボードを上書き。
    - コピーするだけでAIが回答を返してくれます。
    - テキスト問題・計算問題・記述問題を想定しています。

3. 多数決（P2P）
    - UDP ブロードキャスト多数決（`core/network.py`）。
    - 高周波トーン多数決（`core/audio_network.py`、`numpy` + `pyaudio`）。
    - 集計状況はメニューバートレイに表示されます。

4. 問題番号の共有
    - `--host` 起動時のみ問題番号の増減と配信が可能。
    - UDP と高周波の両経路で問題番号変更イベントを配信。

5. パニック表示
    - 緊急ホットキーで謝罪画面を全画面表示し、投票状態をリセット。

## 技術スタック

- Python 3.10+
- PyQt6（GUI、トレイ、ダイアログ）
- mss（画面キャプチャ）
- pynput（グローバルホットキー）
- google-genai（Gemini API）
- keyring（API キー保存）
- UDP broadcast（ローカル P2P）
- numpy / pyaudio（高周波トーン送受信）

## ディレクトリ構成

```text
main.py
core/
    ai_client.py
    audio_network.py
    capture.py
    credentials.py
    hotkey_config.py
    network.py
    notifier_macos.py
    notifier_windows.py
    stealth_notifier.py
ui/
    apology_window.py
    overlay_window.py
    setup_dialog.py
    tray_icon.py
utils/
    key_listener.py
    selection.py
tests/
scripts/
installer/
docs/
assets/
```

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` には必要に応じて以下を設定します。

```dotenv
GEMINI_API_KEY=your_api_key_here
```

## API キーの読み込み順

起動時は次の優先順位で API キーを取得します。

1. keyring に保存済みのキー
2. 環境変数 `GEMINI_API_KEY`（`.env` 含む）

どちらも未設定の場合はセットアップダイアログが表示され、保存したキーは keyring に記録されます。

## 起動

通常起動:

```bash
source .venv/bin/activate
python main.py
```

ホスト起動（問題番号変更を配信可能）:

```bash
source .venv/bin/activate
python main.py --host
```

## ホットキー（既定値）

| 操作 | macOS | Windows/Linux |
|---|---|---|
| AI回答（スクリーンキャプチャ） | Cmd+Shift+Space | Ctrl+Shift+Space |
| クリップボードAI置換 | Cmd+Shift+C | Ctrl+Shift+C |
| 多数決投票 | Option+1〜4 | Alt+1〜4 |
| 問題番号を進める | Option+↑ | Alt+↑ |
| 問題番号を戻す | Option+↓ | Alt+↓ |
| 緊急謝罪 | Cmd+Shift+A | Ctrl+Shift+A |
| アプリ終了 | Cmd+Shift+X | Ctrl+Shift+X |

## ホットキー設定

初回起動時に設定ファイル `hotkeys.json` が自動生成されます。

- macOS: `~/Library/Application Support/InputMonitor/hotkeys.json`
- Windows: `%APPDATA%/InputMonitor/hotkeys.json`
- Linux: `~/.config/input_monitor/hotkeys.json`

設定例:

```json
{
    "version": 1,
    "hotkeys": {
        "ai_answer": "mod+shift+space",
        "copy_hijack": "mod+shift+c",
        "panic": "mod+shift+a",
        "quit": "mod+shift+x",
        "vote_1": "alt+1",
        "vote_2": "alt+2",
        "vote_3": "alt+3",
        "vote_4": "alt+4",
        "question_up": "alt+up",
        "question_down": "alt+down"
    },
    "flags": {
        "audio_vote_enabled": true
    }
}
```

`mod` は macOS では Cmd、それ以外では Ctrl として解釈されます。

## テスト

```bash
source .venv/bin/activate
python -m pytest tests/
# または
python -m unittest discover tests/
```

## ビルド

```bash
pip install -r requirements-build.txt
python build.py
python build.py --skip-package
```

生成物（OS により異なる）:

- macOS: `dist/CunningApp.dmg`
- Windows: `dist/CunningApp_Setup.exe`

## 実行上の注意

- macOS はアクセシビリティ権限（pynput）と画面収録権限（mss）が必要です。
- 高周波多数決は `numpy` と `pyaudio` が利用できない環境では自動的に無効化されます。
- Gemini API のレート制限・課金条件は利用プランに依存します。

## ライセンス

MIT License
