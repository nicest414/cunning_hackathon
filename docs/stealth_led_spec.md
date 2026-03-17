# ステルスLED通知 仕様書

## 1. 概要

キーボードの Caps Lock LED をステルス通知チャネルとして利用する機能。
AI 回答をキーボードの LED 点滅パターンで第三者に伝えることができる。

**OS の論理 Caps Lock 状態は一切変更しない。** LED の物理状態のみを直接制御する。

---

## 2. 対応プラットフォーム

| OS      | 実装ファイル                | 方式                          | 追加権限                          |
|---------|-----------------------------|-------------------------------|-----------------------------------|
| Windows | `core/notifier_windows.py`  | `DeviceIoControl` + `IOCTL_KEYBOARD_SET_INDICATORS` | 管理者権限推奨（UAC） |
| macOS   | `core/notifier_macos.py`    | `IOKit HID API` (ctypes 経由) | アクセシビリティ権限              |
| その他  | フォールバック（何もしない） | —                             | —                                 |

---

## 3. 点滅プロトコル

### 3.1 通常回答通知 `blink(count: int)`

AI が答えを返したとき、選択肢番号（1〜4）を以下のシーケンスで点滅する。

```
[開始シグナル]  高速点滅 × 2回  (ON: 50ms, OFF: 50ms)
[インターバル]  消灯 1000ms
[解答]          ゆっくり count 回点滅  (ON: 300ms, OFF: 200ms)
[終了前待機]    消灯 1000ms
[終了シグナル]  点灯 100ms → 消灯
[リセット]      OS の論理 Caps Lock 状態に戻す
```

### 3.2 リクエスト受理通知 `notify_accepted()`

クリップボード AI 置換のリクエストを受け付けたことを通知する。

```
点灯 500ms → 消灯 → リセット
```

### 3.3 処理完了通知 `notify_ready()`

クリップボード AI 置換の結果が準備できたことを通知する。

```
短く点灯 × 2回  (ON: 100ms, OFF: 100ms) → リセット
```

### 3.4 タイミング定数一覧

| 定数名         | 値      | 説明                     |
|----------------|---------|--------------------------|
| `_START_ON`    | 0.05 s  | 開始シグナル: 点灯時間   |
| `_START_OFF`   | 0.05 s  | 開始シグナル: 消灯時間   |
| `_START_COUNT` | 2 回    | 開始シグナル: 点滅回数   |
| `_INTERVAL`    | 1.0 s   | インターバル消灯時間     |
| `_ANS_ON`      | 0.3 s   | 解答点滅: 点灯時間       |
| `_ANS_OFF`     | 0.2 s   | 解答点滅: 消灯時間       |
| `_END_WAIT`    | 1.0 s   | 終了前消灯時間           |
| `_END_ON`      | 0.1 s   | 終了シグナル: 点灯時間   |

---

## 4. アーキテクチャ

```
main.py
  └─ create_notifier()          # プラットフォームを自動判定してインスタンスを生成
       ├─ Windows → WindowsLEDNotifier
       ├─ macOS   → MacOSLEDNotifier
       └─ その他  → _NullNotifier（何もしない）

AbstractKeyboardLEDNotifier     # 点滅プロトコル・排他制御・キャンセル機構
  ├─ blink(count)               # 別スレッドで非同期実行
  ├─ notify_accepted()
  ├─ notify_ready()
  ├─ reset()                    # OS 論理状態に LED を復元
  └─ cancel()                   # 実行中プロトコルをキャンセル

WindowsLEDNotifier (Windows)
  └─ set_led(state) : DeviceIoControl → IOCTL_KEYBOARD_SET_INDICATORS

MacOSLEDNotifier (macOS)
  └─ set_led(state) : IOHIDManagerCreate → IOHIDDeviceSetValue (HID LED element)
```

### 排他制御

`threading.Lock` による排他制御で、プロトコル実行中に `blink()` が再度呼ばれても無視する。
`cancel()` を呼ぶと進行中のプロトコルが中断し、リセットが実行される。

---

## 5. Windows 実装詳細

### 方式

`kernel32.CreateFileW` でキーボードデバイスを直接オープンし、`DeviceIoControl` に `IOCTL_KEYBOARD_SET_INDICATORS` (0x000b0008) を渡して LED フラグを設定する。

### デバイスパス（試行順）

```
\\?\GLOBALROOT\Device\KeyboardClass0
\\?\GLOBALROOT\Device\KeyboardClass1
\\?\GLOBALROOT\Device\KeyboardClass2
\\.\KeyboardClass0
\\.\KeyboardClass1
```

### LED フラグ

| フラグ                      | 値     |
|-----------------------------|--------|
| `KEYBOARD_CAPS_LOCK_ON`     | 0x0004 |
| `KEYBOARD_NUM_LOCK_ON`      | 0x0002 |
| `KEYBOARD_SCROLL_LOCK_ON`   | 0x0001 |

### 注意事項

- `CreateFileW` には `GENERIC_WRITE` のみを指定（`GENERIC_READ` を追加すると Sharing Violation になることがある）
- 論理 Caps Lock 状態の取得には `user32.GetKeyState(VK_CAPITAL=0x14)` を使用

---

## 6. macOS 実装詳細

### 方式

`IOKit.framework` および `CoreFoundation.framework` を `ctypes` 経由で呼び出す。
HID マネージャーでキーボードデバイスを列挙し、LED エレメント (Usage Page: 0x08 / Usage: 0x02) に対して `IOHIDDeviceSetValue` で値をセットする。

### HID デバイスマッチング

キーボードデバイスを絞り込むためのマッチング辞書:

| キー              | 値                                       |
|-------------------|------------------------------------------|
| `DeviceUsagePage` | `0x01` (HID Generic Desktop Controls)   |
| `DeviceUsage`     | `0x06` (Keyboard)                        |

### LED エレメントの特定

`IOHIDDeviceCopyMatchingElements` は `CFArrayRef` を返す。
配列をイテレートし、以下の条件を満たすエレメントを Caps Lock LED として識別する:

| プロパティ     | 期待値  | 意味                        |
|----------------|---------|-----------------------------|
| `UsagePage`    | `0x08`  | HID LED Usage Page          |
| `Usage`        | `0x02`  | Caps Lock LED               |

### 論理状態の取得

`Carbon.framework` の `GetCurrentKeyModifiers()` を呼び出し、bit `0x0400`（alphaLock）で論理 Caps Lock 状態を判定する。

### 権限要件

- **アクセシビリティ権限**: システム設定 > プライバシーとセキュリティ > アクセシビリティ にターミナル/IDE を追加
- 権限がない場合でも初期化は継続するが、LED 制御が失敗することがある（`stderr` に警告を出力）

---

## 7. ファイル構成

```
core/
  stealth_notifier.py      # 抽象基底クラス・点滅プロトコル・factory
  notifier_windows.py      # Windows 向け実装
  notifier_macos.py        # macOS 向け実装
tests/
  test_stealth_notifier.py # ユニットテスト（OS に依存しないモックベース）
scripts/
  test_stealth_led.py      # 実機動作確認スクリプト
```

---

## 8. 動作確認

```bash
source .venv/bin/activate
python scripts/test_stealth_led.py
```

実行するとキーボードの Caps Lock ランプが点滅プロトコル（3回点滅）を実行する。
論理的な Caps Lock の状態が変わっていないことを確認すること。

### macOS での注意事項

初回実行時は以下のメッセージが表示される場合がある:

```
[LED] 警告: アクセシビリティ権限がありません。
  システム設定 > プライバシーとセキュリティ > アクセシビリティ に
  このターミナル（または IDE）を追加してください。
```

アクセシビリティ権限を付与してから再度実行すること。
