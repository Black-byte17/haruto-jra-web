# レース別成果物

`/haruto-jra-forecast` が1レースごとに `<YYYYMMDD>_<場><R>/` フォルダを作る。

```
20261012_京都11R/
├── run_log.md        実行ログ（マスター読込・入力・担当の起動記録・凍結ハッシュ）
├── agents/           専門エージェント13体の担当ログ
├── sim/              展開シミュレーションのコード・seed・出力（実行した場合のみ）
├── ev/               券種別確率・EV計算のコードと出力（実行した場合のみ）
├── internal_draft.md Chief の統合案
├── internal.md       内部版（ユーザー向け詳細版）
├── note.md           note公開版
├── compliance.md     Protocol Compliance Supervisor の最終監査
├── frozen/           発走前の凍結版（上書き禁止）
└── verification.md   結果検証（レース後に別途作成）
```
