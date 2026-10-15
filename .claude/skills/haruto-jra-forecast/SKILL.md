---
name: haruto-jra-forecast
description: |
  【HARUTO JRA 中枢・完全予想／結果検証】haruto/MASTER_PROMPT.md（V19）を全文適用し、メインセッションが
  Chief Orchestrator となって13人の専門エージェント（.claude/agents/haruto-*）を起動し、全22PHASE・14担当・
  TRIPLE CHECK・3 Whys・5仮説・最終監査・note公開版まで実行する。
  使う場面：JRAレースの予想（「完全予想」「HARUTOで予想」「◎○▲」「買い目」「note版」）、
  JRAレースの結果検証（「検証して」「なぜ外れたか」）、中枢マスターの改訂（「マスターに追記」）。
  JRA の予想・検証では rt6-prediction や旧 haruto-prediction v4.0.1 より本スキルを優先する。
  地方競馬（NAR）と競馬以外のタスクには使わない。
---

# HARUTO JRA 完全予想ワークフロー（Chief Orchestrator 手順書）

このスキルを使うとき、**メインセッションのあなたが Chief Orchestrator** である。
中枢は `haruto/MASTER_PROMPT.md`。このスキルは「マスターを漏れなく実行するための段取り」であり、
規則の中身はマスターが正。両者が食い違えばマスター（V19優先）に従う。

## モードの判定

| モード | きっかけ | 違い |
|---|---|---|
| **予想** | 発走前のレースの予想依頼 | 発走前情報のみ。結果は遮断。最後に凍結版を作る |
| **事後分析** | 結果が既に出ているレースの予想依頼 | 全出力に【事後分析】と表示し、事前予想の的中と呼ばない |
| **検証** | 結果照合・反省の依頼 | 凍結済みの発走前版だけを対象に照合（マスター17章・V18第5節4） |
| **改訂** | マスターへの追記・変更の依頼 | 下の「マスター改訂」へ |

---

## STEP 0　中枢マスターの全文読込【省略禁止】

1. `haruto/MASTER_PROMPT.md` を Read で **1行目から1136行目（最終行）まで** 分割して読む（例：1–300, 300–600, 600–900, 900–1136）。行数が変わっていれば `wc -l` で確認して最後まで読む。
2. `sha256sum haruto/MASTER_PROMPT.md` を取り、CLAUDE.md / `haruto/CHANGELOG.md` の記録値と比べる。違えば改訂履歴を確認し、ユーザーに報告する。
3. 版（V19）、読了行、ハッシュ、採用した追補、競合の解決（V19 > V18.3 以前）を `run_log.md` に記録する。
4. 読み切れなかった場合は「マスター全文未読」と明示し、`PASS` を出さない。

## STEP 1　PRE-FLIGHT（レースフォルダと入力）

1. レースフォルダを作る：`haruto/races/<YYYYMMDD>_<場><R>/`（例 `haruto/races/20261012_京都11R/`）と `agents/`・`sim/`・`ev/` サブフォルダ。
2. `templates/run_log.md` をコピーして `run_log.md` を作り、開催日・場・R・発走時刻・予想時刻（`date` で JST 取得）・モードを記入。
3. ユーザーの添付ファイル（RT6・TARGET★6/SENREKI/TIME/LAP・Oikiri・オッズ・馬場情報）の場所を確認。添付が無いものは不足リストに入れ、**ユーザーに提供を依頼する文面**を用意する（作業は止めず、取れる範囲で進める）。
4. 結果が既に出ていないか確認し、出ていれば【事後分析】モードに切り替える。

## STEP 2　専門エージェントの起動（Agent ツールで実際に起動）

各エージェントへのプロンプトには必ず以下を含める：
`レースフォルダのパス／モード／開催日・場・R・発走時刻・予想締切／入力ファイルのパス一覧／「haruto/MASTER_PROMPT.md の指定箇所を自分で読むこと」／出力先 agents/<名前>.md`。

**第1波（単独・先行）**
- `haruto-data-intelligence`：入力監査・出走全馬一覧・列の時点分類・結果遮断。→ 結果を全担当に共有する。

**第2波（並列：1つのメッセージで同時に起動）**
- `haruto-rt6-rotation`（PHASE02）
- `haruto-lap-speed`（PHASE03・11）
- `haruto-pace-simulation`（PHASE06・10）
- `haruto-track-bias`（PHASE07・08）
- `haruto-bloodline`（PHASE09）
- `haruto-jockey`（PHASE12）
- `haruto-condition-training`（PHASE13）
- `haruto-market-odds`（PHASE05・17）

PHASE04（過去10年同条件）は第2波のうち `haruto-lap-speed`（同条件時計）と `haruto-market-odds`（人気・配当傾向）に分担させ、10年データ（`JRA_10YEARS_RESULT.csv` 等）が添付されていなければ NOT-AVAILABLE とする。

**Chief 統合①（PHASE11・14・15・16・19 の素案）**
- 全担当ファイルを読み、V19 の順で統合：**①能力 → ②展開 → ③追切 → ④近走 → ⑤馬場 → ⑥期待値**。
- `haruto-rt6-rotation` を再度起動して PHASE14（他担当の結果による RT6 仮説の支持／反証／修正）を行わせる。
- 全馬評価表・能力順位（市場と独立）・5仮説×3ペース・穴馬／危険人気馬の素案・**最終印案（◎○▲☆＋△最大3＝7頭以内）** を `internal_draft.md` に書く。

**第3波（並列）**
- `haruto-ev-probability`（PHASE18・20：最終印案からA群・B群の全候補EV）
- `haruto-risk-supervisor`（PHASE15・16・20：穴馬・危険人気馬・買い目集合の監査）

**Chief 統合②（PHASE19・20）**
- 印を確定し、買い目（馬連0〜5点・ワイド0〜5点・三連系は必要時のみ・単複なし）と BET／NO BET を決めて `internal_draft.md` を更新。

**第4波（直列）**
1. `haruto-red-team`：反証・3 Whys・ゼロベース再判定（TRIPLE CHECK ②③）。→ Chief が差異を検討し、印・買い目を変えるなら理由を記録。
2. note版を作成（STEP 4）。
3. `haruto-protocol-compliance`：最終監査（PHASE21・22）。`BLOCKED` なら指摘を修正して再監査。

**エージェントを起動できない環境の場合**：同じ担当順で自分が順次検証し、`run_log.md` の担当表に「順次検証（サブエージェント未起動）」と書く。「14エージェント並列実行済み」とは書かない。

## STEP 3　内部版（ユーザー向け詳細版）の作成

`internal.md` に、マスター冒頭Dと V18.3-5 の順序で書く：

入力／データ時点 → 22PHASE別状態表（`templates/phase22_status.md`）→ 14担当別所見 → 全馬評価 → 能力順位と展開別評価 → 追切／近走／馬場 → 危険人気馬／穴馬 → TRIPLE CHECK差異（通常・反証・ゼロベース）と3 Whys・5仮説・Deep Dive 3段階 → 最終印（◎○▲☆△ 合計7頭以内）→ 買い目候補EV比較表（A群・B群）→ 採用買い目（券種・点数・購入額）・◎軸依存率 → 総投資・予想総期待利益/ROI（算出可能時）→ BET／NO BET → 最終監査結果・不足項目。

証拠区分（CONFIRMED / RECALLED / UNVERIFIED / EXPERIMENTAL / VALIDATED）と未取得・未実行を明示する。

## STEP 4　note公開版の作成

`note.md` を `templates/note.md` の形式で作る（縦型・表なし）。

①レース情報 → ②🏇最終予想 → ③⚠️危険人気馬 → ④🔥注目穴馬 → ⑤🔑最重要馬 → ⑥🏁最終結論 → ⑦🎯私の馬券構築 → ⑧`※ あくまで予想です。馬券の購入はご自身の判断でお願いします。`

内部用語を出さない。保存後に必ず秘匿チェックを実行する：

```bash
grep -nE 'MASTER|HARUTO|RT6|TARGET|Oikiri|着RT|人RT|展RT|能力M|能平均|平脚|SP順|3FMax|PHASE|Agent|エージェント|Signal|Consensus|Divergence|EV|期待値率|損益分岐|公正オッズ|10,?000回|TRIPLE|Protocol|Compliance|LightGBM|Plackett' haruto/races/<フォルダ>/note.md
```

ヒットがあれば一般的な競馬用語に言い換える。印・買い目・BET/NO BET は内部版と完全一致させる。

## STEP 5　凍結と報告

1. 予想モードでは `frozen/` に `internal.md`・`note.md`・`run_log.md` をコピーし、`sha256sum` を `run_log.md` に記録（予想時刻つき）。凍結後は上書きしない。追加情報で再評価した場合は `v2` として別に凍結する。
2. ユーザーへの返答：最終印・買い目（またはNO BET）・Compliance 判定（PASS／PARTIAL／BLOCKED と理由）・不足データと取得方法・note版の場所。
3. ユーザーが望めば git にコミット・プッシュする（作業ブランチのルールに従う）。

---

## 検証モード

1. 対象レースの `frozen/` を読む。凍結版が無ければ「事前予想の記録なし」として成績に含めない。
2. `templates/verification.md` に沿って：①最終印と全馬着順 ②最終確定買い目の的中 ③購入額 ④実払戻 ⑤回収率 ⑥展開・馬場・馬体重・追切・相手関係・市場乖離 ⑦削除した的中買い目、を別々に評価。印の捕捉率と買い目の収支を分ける。
3. なぜ×3で原因を掘り、改善案は `EXPERIMENTAL` としてマスター改訂候補に出す。凍結版は書き換えない。
4. 同日複数レースの場合は `haruto/races/<YYYYMMDD>_summary.md` に集計。

## マスター改訂

1. ユーザーが明示した変更だけを、マスター末尾に **Append-only** で追補（版名・日付・変更理由・競合の解決）。既存条文は消さない。
2. `haruto/CHANGELOG.md` に日付・版・要旨・新しい SHA-256 を追記し、CLAUDE.md のハッシュ値も更新。
3. 改訂がエージェントの担当範囲に影響するなら `.claude/agents/haruto-*.md` の「マスター参照箇所」も更新する。
