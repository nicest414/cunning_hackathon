# CLAUDE.md

## プロジェクト概要

ハックツハッカソン メガロカップ出展作品。四択テスト画面をキャプチャして Gemini AI に回答させ、透明オーバーレイに表示するネタアプリ。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # GEMINI_API_KEY を設定
```

## 起動

```bash
source .venv/bin/activate
python main.py
# 終了: Ctrl+C
```

## テスト

```bash
source .venv/bin/activate
python -m pytest tests/
# または
python -m unittest discover tests/
```

## ビルド（配布用パッケージ生成）

```bash
# ビルド環境のセットアップ
pip install -r requirements-build.txt

# macOS → dist/CunningApp.dmg を生成
python build.py

# Windows → dist/CunningApp_Setup.exe を生成
python build.py

# ビルドのみ（パッケージ化をスキップ）
python build.py --skip-package
```

## 技術スタック

- **Python 3.10+**
- **PyQt6** — GUI・透明オーバーレイ
- **mss** — 画面キャプチャ
- **pynput** — グローバルホットキー
- **google-genai** — Gemini 1.5 Flash API
- **python-dotenv** — 環境変数管理
- **UDP broadcast** — P2P 多数決通信（サーバーレス）

## ディレクトリ構成

```
main.py                  # エントリーポイント・モジュール初期化
core/
  ai_client.py           # Gemini API 呼び出し・回答解析
  capture.py             # mss による画面キャプチャ
  network.py             # UDP ブロードキャスト送受信
ui/
  overlay_window.py      # 回答表示用透明オーバーレイ
  apology_window.py      # 謝罪全画面ウィンドウ
utils/
  key_listener.py        # グローバルホットキー登録・管理
assets/
  sorry.png              # 緊急謝罪画像
tests/
  test_ai_client.py      # ai_client ユニットテスト（genai モック済み）
  test_capture.py        # capture ユニットテスト
  test_key_listener.py   # KeyListener ユニットテスト
  test_network.py        # VoteNetwork ユニットテスト
```

## ホットキー

| 操作 | macOS | Windows/Linux |
|---|---|---|
| AI回答（スクリーンキャプチャ） | `Cmd+Shift+Space` | `Ctrl+Shift+Space` |
| クリップボードAI置換 | `Cmd+C` | `Ctrl+C` |
| 多数決投票 | `Option+1〜4` | `Alt+1〜4` |
| 緊急謝罪 | `Cmd+Shift+A` | `Ctrl+Shift+A` |
| アプリ終了 | `Cmd+Shift+X` | `Ctrl+Shift+X` |

## 環境変数

| 変数 | 説明 |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio で発行した API キー |

## macOS 固有の注意事項

- **アクセシビリティ権限**: システム設定 > プライバシーとセキュリティ > アクセシビリティ にターミナル/IDEを追加（pynput のグローバルフックに必要）
- **画面収録権限**: システム設定 > プライバシーとセキュリティ > 画面収録 にターミナル/IDEを追加（mss のキャプチャに必要）

## アーキテクチャ

- `_Bridge` (QObject) がキーボードスレッド → Qt メインスレッドへのイベント橋渡しを担当
- キーリスナーは別スレッドで動作し、pyqtSignal 経由でメインスレッドに通知
- AI 問い合わせは `threading.Thread` で非同期実行（UI フリーズ防止）
- ネットワーク通信は UDP ブロードキャスト（同一 Wi-Fi 内のみ、サーバー不要）
