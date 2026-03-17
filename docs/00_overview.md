# Step 1 実装計画 — 概要

## 目的

`main.py` が `.env` / 環境変数に直接依存している現状を改め、
**初回起動時に GUI でAPIキーを入力 → OSのセキュアストレージに保存 → 次回以降は自動読み込み**
というライフサイクルへ移行する。

## 対象ファイル（新規 or 変更）

| # | ドキュメント | 対象ファイル | 種別 |
|---|---|---|---|
| 1 | `step1_credentials.md` | `core/credentials.py` | 新規作成 |
| 2 | `step1_credentials.md` | `tests/test_credentials.py` | 新規作成 |
| 3 | `step2_setup_dialog.md` | `ui/setup_dialog.py` | 新規作成 |
| 4 | `step3_main_refactor.md` | `main.py` | 変更 |
| 5 | `step3_main_refactor.md` | `requirements.txt` | 変更（keyring 追加） |
| 6 | `step4_build_spec.md` | `installer/app.spec` | 新規作成 |
| 7 | `step4_build_spec.md` | `installer/build_mac.sh` | 新規作成 |
| 8 | `step4_build_spec.md` | `installer/installer.iss` | 新規作成 |
| 9 | `step5_build_script.md` | `build.py` | 新規作成 |
| 10 | `step5_build_script.md` | `requirements-build.txt` | 新規作成 |

## 実行順序

```
step1_credentials.md  →  step2_setup_dialog.md  →  step3_main_refactor.md
  →  step4_build_spec.md  →  step5_build_script.md
```

各ドキュメントを **1つずつ順に** Claude Code に投げること。
前のステップが完了してから次に進むこと（依存関係があるため）。

## 完了基準

- `python -m pytest tests/` が全てパスする
- `python main.py` を初回起動時（keyring にキーなし）に実行すると SetupDialog が表示される
- APIキー入力・保存後、MainWindow（既存の overlay）が起動する
- 2回目以降の起動では SetupDialog が表示されず直接起動する
- `.env` の `GEMINI_API_KEY` は **フォールバックとして引き続き動作する**（既存環境への後方互換）
