# haruto-jra-web — プロジェクト中枢

このリポジトリは2つの役割を持つ。

1. **HARUTO 競馬予想 JRA の中枢（予想・検証プロジェクト）** — `haruto/`
2. **予想Webアプリ（Flask）** — `app.py` / `templates/` / `static/`（Render へデプロイ。`Procfile`・`render.yaml`）

---

## 1. HARUTO JRA 中枢【競馬の予想・検証では最優先で適用】

### 中枢文書

- **`haruto/MASTER_PROMPT.md`** が唯一の中枢マスター（現行 **V19 / 2026-10-12・能力主導・全22PHASE監査**）。
  - SHA-256: `73e6d37acaf0ca7c7e6987743344e1ff70e240d642dc826d41f4737b19ffcd76`（保存時の値。改訂後は `haruto/CHANGELOG.md` に新しい値を記録）
  - 優先順位：**冒頭のV19運用規定 > 末尾のV19追補 > V18.3以前の競合条文**。旧版の条文は削除せず監査記録として保持する。
- 改訂は **Append-only**。ユーザーが明示した変更だけを反映し、変更内容は `haruto/CHANGELOG.md` に追記する。マスター本文の既存条文を削除・要約・書き換えしない。

### JRAの予想・検証を頼まれたら必ずやること

1. **`/haruto-jra-forecast` スキルを起動する**（「HARUTO」「完全予想」「◎○▲」「買い目」「結果検証」など、JRAレースの予想・検証の依頼すべてが対象）。
2. スキルの手順に従い、**`haruto/MASTER_PROMPT.md` を毎回すべて読む**（1,136行を分割して最後の行まで）。要約や記憶だけで「全マスター適用」と言わない。
3. メインのセッションが **Chief Orchestrator** を担い、`.claude/agents/` の13人の専門エージェントを Agent ツールで実際に起動する（下表）。起動しなかった担当は「順次検証」と明記し、「14エージェント並列実行済み」とは書かない。
4. 最優先の順位：**①能力 → ②展開 → ③追切 → ④近走 → ⑤馬場 → ⑥期待値**（V19）。期待値は買い目採否の最終層であり、能力上位馬を印から消す根拠にしない。
5. 成果物は `haruto/races/<YYYYMMDD>_<場><R>/` に保存（内部版・note版・監査票・凍結版）。発走前版は凍結し、結果後に上書きしない。

### 専門エージェント配置（`.claude/agents/`）

| マスター上の担当 | エージェント名 | 主なPHASE |
|---|---|---|
| Chief Orchestrator | **メインセッション**（スキル `haruto-jra-forecast` が手順書） | 全体・01・19・22 |
| Data Intelligence | `haruto-data-intelligence` | Data Audit Gate・01 |
| RT6 & Rotation | `haruto-rt6-rotation` | 02・14 |
| Pace / Simulation | `haruto-pace-simulation` | 06・10 |
| Lap / Speed | `haruto-lap-speed` | 03・11 |
| Track Bias | `haruto-track-bias` | 07・08 |
| Bloodline | `haruto-bloodline` | 09 |
| Condition / Training | `haruto-condition-training` | 13 |
| Jockey | `haruto-jockey` | 12 |
| Market / Odds | `haruto-market-odds` | 05・17 |
| EV / Probability | `haruto-ev-probability` | 18・20 |
| Risk Supervisor | `haruto-risk-supervisor` | 15・16・20 |
| Red-Team | `haruto-red-team` | 21（反証） |
| Protocol Compliance Supervisor | `haruto-protocol-compliance` | 21・22（最終ゲート） |

※ Claude Code のサブエージェントは別のサブエージェントを起動できないため、Chief はメインセッションが担当する。

### 絶対禁止（マスター V19-4・V18.3-5 の失格条件）

- 未読のマスターを「読込済み」とすること、未取得データ・未実行計算（10年ML推論・10,000回試行・オッズ・追切時計・通過順）を捏造すること。
- 結果を知ってから事前予想を書き換えること（後知恵）。結果既知のレースは【事後分析】と表示する。
- 22PHASEが未完了なのに `PASS：完全実行` とすること。
- note公開版に内部情報（MASTER_PROMPT、HARUTO内部名、RT6/TARGET/Oikiri、着RT等の固有指標、PHASE、Agent、EV%、10,000回、TRIPLE CHECK 等）を出すこと。
- 最終印7頭超、馬連・ワイド各5点超、単勝・複勝の推奨。

### 関連スキルとの関係

- `rt6-prediction`（`.claude/skills/rt6-prediction/`）：RT6作者の運用法。HARUTO予想では `haruto-rt6-rotation` が**参考層**として使う。RT6単独で最終判定しない。
- ユーザー環境の `haruto-prediction` v4.0.1（JRA/NAR汎用の旧スキル）：**JRAでは本中枢V19を優先**。NAR（地方競馬）はマスター0章のとおり別モデル扱いで、本中枢を無条件に流用しない。

---

## 2. Webアプリ（Flask）

- `app.py`：netkeiba 等から出馬表をスクレイピングし、独自スコア（`calc_score` / `calc_nar_score`）で印を付ける。ルート `/`・`/jra`・`/nar`・`/api/races`・`/api/predict`。
- 依存：`requirements.txt`（flask / requests / beautifulsoup4 / gunicorn）。ローカルは `start_local.bat` または `python app.py`。
- アプリのスコアロジックは簡易版であり、中枢マスターの22PHASE予想とは別物。マスターの規則をアプリに実装する場合は「プロンプト仕様」と「実装・検証済みモデル」を分離する（マスター18章）。
