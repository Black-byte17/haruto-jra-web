# 実行ログ — 2026-10-17 東京 4回6日 11R 富士ステークス(G2)

| 項目 | 内容 |
|---|---|
| モード | 予想（発走前・結果未確定） |
| 発走時刻 | 2026-10-17 15:45 JST |
| 予想開始時刻（JST） | 2026-10-17 01:36:35 |
| 予想締切（cutoff） | 凍結時刻（本ログ末尾）。使用オッズの最終観測は 01:30 |
| マスター | haruto/MASTER_PROMPT.md　版: V19　読了行: 1–1136（Read 4分割: 1–300 / 300–599 / 600–899 / 900–1136）　SHA-256: 73e6d37acaf0ca7c7e6987743344e1ff70e240d642dc826d41f4737b19ffcd76（CLAUDE.md/CHANGELOGと一致） |
| 採用追補・競合解決 | V19冒頭規定 > V19追補 > V18.3以前。印=能力→展開→追切→近走→馬場、期待値は第6層（買い目採否） |

## 入力ファイル（haruto/races/20261017_東京11R/input/）
| ファイル | 種類 | 文字コード | 行数 | SHA-256(先頭16) | 時点区分 |
|---|---|---|---|---|---|
| raw_26.10.17_oikiri.csv → 26.10.17_oikiri.utf8.csv | Oikiri追切（全場10/17分） | UTF-8 BOM付 | 46,651 | 2ea190091988622f | PRE_RACE（FetchedAt要監査） |
| raw_261017_11R_hoshi6.csv → *.utf8.csv | TARGET★6 | CP932 | 15 | ff533bd079f1b720 | PRE_RACE |
| raw_261017_11R_rapu.csv → *.utf8.csv | TARGET LAP（過去走レースラップ） | CP932 | 126 | bee0fc818f4759c2 | PRE_RACE（過去走のみ） |
| raw_261017_11R_sennreki1.csv → *.utf8.csv | TARGET SENREKI_1 | CP932 | 126 | 346b0b80393dc238 | PRE_RACE（過去走のみ） |
| raw_261017_11R_sennreki2.csv → *.utf8.csv | TARGET SENREKI_2 | CP932 | 126 | 22624c41f70ee2dd | PRE_RACE（過去走のみ） |
| rt6_tables.tsv | RT6表（チャット貼付を転記） | UTF-8 | — | 3be0c385179dd500 | PRE_RACE（スナップ時刻不明） |
| odds_timeseries.md | 時系列オッズ 単勝/複勝/馬連（貼付を転記、馬連は01:30行のみ） | UTF-8 | — | 569569e7065eadfd | PRE_RACE 前売り（最終観測01:30） |
| track_condition.md / track_image_1.png(=2.png 同一) | 金曜昼の馬場状態＋見解 | — | — | e384869b297d38fd / 652e5d75afda215f | 前日資料 |

## 不足データ・ユーザーへの依頼
- ワイド・三連複・三連単の時系列オッズ（発走前）→ 馬券EVに必須。時系列オッズソフトで同形式の出力を依頼
- 発走直前（締切前）の単勝・馬連オッズ（01:30は前売り小プール）
- 当日（10/17）東京芝の既施行レース全馬通過順・上がり（11R発走前に確定分）
- 当日馬体重（14:40頃発表）
- TARGET TIME（区間時計）・過去10年の富士S/東京芝1600m重賞データ（JRA_10YEARS_RESULT.csv等）

## 担当の起動記録（14担当）
（下に追記）
