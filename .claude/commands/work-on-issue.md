Issue #$ARGUMENTS の内容を読み込み、実装作業を開始してください。

以下の手順で進めてください：

## 1. Issue の内容確認

```bash
gh issue view $ARGUMENTS
```

Issue のタイトル・本文・ラベル・担当者・コメントをすべて確認してください。

## 2. 関連情報の収集

- Issue に関連する既存コードをコードベースから探し、理解する
- 関連する他の Issue や PR があれば確認する (`gh issue list`, `gh pr list`)
- 現在のブランチとgit statusを確認する

## 3. 作業ブランチの作成

Issue の内容に沿った命名でブランチを作成してください：

```bash
git checkout main
git pull origin main
git checkout -b <branch-name>
```

ブランチ名の例：
- `feature/issue-$ARGUMENTS-<短い説明>`
- `fix/issue-$ARGUMENTS-<短い説明>`
- `chore/issue-$ARGUMENTS-<短い説明>`

## 4. 実装方針の提示

ブランチ作成後、以下を日本語で説明してください：

- Issue が解決しようとしている問題・目的
- 実装方針（どのファイルをどう変更するか）
- 懸念点や不明点があれば列挙

確認が取れたら実装を開始してください。
