# カンニングアプリ

> **ハックツハッカソン メガロカップ出展作品**
>
> _注意: これはジョーク目的のハッカソン用デモアプリです。実際の試験・テストでの不正行為を推奨するものではありません。当然ですが。_

---

## 概要

四択テストの画面をこっそり撮影し、AIが瞬時に答えを割り出して右下にひっそり表示する**全自動カンニング風ネタアプリ**です。

さらに、同じWi-Fi内のユーザーと答えを持ち寄って多数決を取る P2P 機能や、先生が近づいてきたときのための**緊急謝罪モード**まで完備。あらゆる「まずい」場面に対応します。

---

## 主な機能

### 1. AI回答機能 — `Cmd+Shift+Space` / `Ctrl+Shift+Space`

画面全体を自動キャプチャし、Google Gemini 3.1 Flash に送信。
AIが四択の番号を判定し、**クリックすり抜け設定の透明オーバーレイ**に回答をひっそり表示します。
オーバーレイはウィンドウ最前面に配置されており、画面の操作を一切邪魔しません。

### 2. 多数決機能 — `Option+1〜4` / `Alt+1〜4`

UDPブロードキャストを使用したサーバーレス P2P 通信で、同じWi-Fi内の端末と回答を共有。
全参加端末の回答をリアルタイム集計し、多数派の選択肢をオーバーレイに表示します。
サーバー不要・設定不要。ルーターさえあれば即席の集合知が完成します。

### 3. 証拠隠滅 & 謝罪機能 — `Cmd+Shift+Q` / `Ctrl+Shift+Q`

**バレそうになったとき専用の緊急脱出ボタン。**
キーを押した瞬間にすべてのオーバーレイを消去し、画面中央に `assets/sorry.png` を全画面表示。
疑惑を「誠実さ」で上書きします。

---

## 技術スタック

| 領域 | 技術 |
|---|---|
| 言語 | Python 3.x |
| GUI / オーバーレイ | PyQt6（`Qt.WindowTransparentForInput` + `WA_TranslucentBackground`） |
| 画面キャプチャ | mss |
| キーボード監視 | keyboard |
| AI | Google GenAI SDK（Gemini 1.5 Flash） |
| P2P 通信 | Python 標準 `socket`（UDP ブロードキャスト） |

---

## ディレクトリ構成

```
cunning_hackathon/
├── main.py                  # アプリ起動・各モジュール初期化
├── .env.example             # 環境変数サンプル（Gemini APIキー）
├── requirements.txt         # 依存パッケージ一覧
├── core/
│   ├── ai_client.py         # Gemini API 呼び出し・回答解析
│   ├── capture.py           # mss による画面キャプチャ
│   └── network.py           # UDP ブロードキャスト送受信
├── ui/
│   ├── overlay_window.py    # 回答表示用透明オーバーレイ
│   └── apology_window.py    # 謝罪全画面ウィンドウ
├── utils/
│   └── key_listener.py      # グローバルホットキー登録・管理
└── assets/
    └── sorry.png            # 謝罪画像（重要）
```

---

## セットアップ

> Docker / コンテナは使用しません。
> GUI レンダリングおよびOS レベルのキーボードフックにはホスト環境への直接アクセスが必要なため、`venv` によるローカル環境を推奨します。

### 必要環境

- Python 3.10 以上
- [Google AI Studio](https://aistudio.google.com/) で発行した Gemini API キー
- **macOS の場合**: アクセシビリティ権限（システム設定 > プライバシーとセキュリティ > アクセシビリティ）にターミナル / IDE を追加してください。`keyboard` ライブラリのグローバルフック使用に必要です。
- **Linux の場合**: `keyboard` の使用には `sudo` が必要になる場合があります。

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-org/cunning_hackathon.git
cd cunning_hackathon
```

### 2. 仮想環境の作成と有効化

```bash
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、取得した Gemini API キーを記入します。

```bash
cp .env.example .env
```

```dotenv
# .env
GEMINI_API_KEY=your_api_key_here
```

### 5. 起動

```bash
python main.py
```

起動後はバックグラウンドで動作します。ショートカットキーを押すまで、何も起きません。何も起きていません。

---

## デプロイ（配布用パッケージのビルド）

開発環境なしで動作するスタンドアロン実行ファイルを生成します。PyInstaller でアプリをバンドルし、macOS では `.dmg`、Windows では `.exe` インストーラーを出力します。

### 前提ツール

| OS | 必要なツール | インストール方法 |
|---|---|---|
| macOS | `create-dmg` | `brew install create-dmg` |
| Windows | Inno Setup 6 | `winget install JRSoftware.InnoSetup` |

### 手順

#### 1. ビルド用依存パッケージのインストール

```bash
pip install -r requirements-build.txt
```

#### 2. ビルド実行

```bash
# macOS → dist/CunningApp.dmg を生成
python build.py

# Windows → dist/CunningApp_Setup.exe を生成
python build.py
```

#### パッケージ化をスキップしてバイナリだけ生成したい場合

```bash
python build.py --skip-package
# 成果物: dist/CunningApp/ (実行ファイル込みのディレクトリ)
```

### 成果物

| OS | ファイル | 説明 |
|---|---|---|
| macOS | `dist/CunningApp.dmg` | ドラッグ&ドロップでインストールできる .dmg |
| Windows | `dist/CunningApp_Setup.exe` | Inno Setup 製インストーラー |

> **初回起動時の API キー設定について**
> `.env` ファイルや `GEMINI_API_KEY` 環境変数が未設定の場合、起動時に API キー入力ダイアログ（SetupDialog）が表示されます。入力されたキーは OS のセキュアストレージ（keyring）に保存されるため、2 回目以降の起動時は入力不要です。
> 環境変数 `GEMINI_API_KEY` が設定されている場合はダイアログをスキップして直接起動します。

---

## 注意事項

- **Gemini API の無料枠には利用制限があります。** 連打は控えてください。
- **macOS では画面収録の許可**（システム設定 > プライバシーとセキュリティ > 画面収録）も必要です。
- このアプリは実在する試験・資格・競技等での使用を想定していません。ジョークアプリとしてお楽しみください。
- `sorry.png` の差し替えは自己責任で。

---

## ライセンス

MIT License — ただし、いかなる試験会場への持ち込みも MIT では許可されていません。常識の範囲でご利用ください。
