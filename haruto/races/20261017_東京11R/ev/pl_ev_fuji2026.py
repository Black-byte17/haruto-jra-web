# -*- coding: utf-8 -*-
"""
HARUTO EV / Probability — 2026-10-17 東京11R 富士S(G2) 芝1600m 14頭（予想モード・発走前）
PHASE18/20: Plackett-Luce 着順同時分布 → 馬連/ワイド/三連複/三連単 成立確率 → 馬連EV（01:30前売り）
              ワイド/三連複/三連単は価格なし → 必要最低オッズ=1/p_conservative（EV算定保留）

入力（すべて発走前情報）:
  - 統合スコア: internal_draft.md 第6節（Chief主観統合・EXPERIMENTAL・未校正）
  - 馬連オッズ: input/odds_timeseries.md 01:30 前売り（CONDITIONAL）
  - 市場暗黙確率: ev/market_implied.csv は「比較列」のみ。p には一切使わない。
確率モデル:
  w_i = exp((score_i - mean)/T)、PL のトップ3を厳密列挙（14*13*12=2184 順列）。
  T: 基準16 / 保守24(=1.5x, 平坦化) / 強気11(≈16/1.5)。
  p_conservative = min(p_T11, p_T16, p_T24)（組合せごと、3温度の最小）。
  o_conservative = o_0130 * 0.90（締切までの10%価格下落を仮定）。
検算: seed=20261017 で PL を 200,000 回サンプリング（Gumbel-max）し厳密値と比較。
依存: Python 標準ライブラリのみ（numpy 非搭載環境）。
"""
import csv, itertools, math, os, random, json, hashlib, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RACE = os.path.dirname(HERE)

SEED = 20261017
N_MC = 200_000
T_BASE, T_CONS, T_AGGR = 16.0, 24.0, 11.0
TEMPS = {"T11_aggr": T_AGGR, "T16_base": T_BASE, "T24_cons": T_CONS}
ODDS_DROP = 0.90
ODDS_RISE = 1.10

NAMES = {1: "ファンダム", 2: "ミトノオルフェ", 3: "シンフォーエバー", 4: "トロヴァトーレ",
         5: "アドマイヤズーム", 6: "デビットバローズ", 7: "ウォーターリヒト", 8: "マジックサンズ",
         9: "キープカルム", 10: "アンパドゥ", 11: "ファーヴェント", 12: "エンペラーズソード",
         13: "シュガークン", 14: "エコロアルバ"}
# internal_draft.md 第6節 統合スコア（EXPERIMENTAL）
SCORE = {5: 82, 4: 80, 10: 77, 7: 66, 14: 66, 9: 63, 1: 63, 8: 58, 11: 56, 12: 50,
         6: 45, 2: 38, 13: 35, 3: 30}
MARKS = {5: "◎", 4: "○", 10: "▲", 7: "☆", 14: "△", 9: "△", 1: "△"}
HONMEI = 5
MARKED = sorted(MARKS)  # [1,4,5,7,9,10,14]
HORSES = sorted(SCORE)
assert len(HORSES) == 14 and len(MARKED) == 7


def load_quinella_odds():
    path = os.path.join(RACE, "input", "odds_timeseries.md")
    odds, on = {}, False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("## 馬連"):
                on = True
                continue
            if on and line.startswith("##"):
                break
            if on and "\t" in line and line[0].isdigit():
                c, o = line.split("\t")
                a, b = map(int, c.split("-"))
                odds[frozenset((a, b))] = float(o)
    assert len(odds) == 91, len(odds)
    return odds


def load_market():
    path = os.path.join(RACE, "ev", "market_implied.csv")
    win, q = {}, {}
    with open(path, encoding="utf-8") as f:
        rows = [l for l in f if not l.startswith("#")]
    for r in csv.DictReader(rows):
        if r["bet_type"] == "単勝":
            win[int(r["combination"])] = float(r["normalized_implied"])
        elif r["bet_type"] == "馬連":
            a, b = map(int, r["combination"].split("-"))
            q[frozenset((a, b))] = float(r["normalized_implied"])
    return win, q


def strengths(T):
    m = sum(SCORE.values()) / len(SCORE)
    return {h: math.exp((SCORE[h] - m) / T) for h in HORSES}


def exact_top3(w):
    """PL の (1着,2着,3着) 厳密確率。"""
    Z = sum(w.values())
    tri = {}
    for i in HORSES:
        pi = w[i] / Z
        Z1 = Z - w[i]
        for j in HORSES:
            if j == i:
                continue
            pj = w[j] / Z1
            Z2 = Z1 - w[j]
            for k in HORSES:
                if k == i or k == j:
                    continue
                tri[(i, j, k)] = pi * pj * (w[k] / Z2)
    return tri


def derive(tri):
    win = {h: 0.0 for h in HORSES}; top2 = dict(win); top3 = dict(win)
    quin, wide, trio = {}, {}, {}
    for (i, j, k), p in tri.items():
        win[i] += p
        top2[i] += p; top2[j] += p
        top3[i] += p; top3[j] += p; top3[k] += p
        q = frozenset((i, j)); quin[q] = quin.get(q, 0) + p
        for a, b in ((i, j), (i, k), (j, k)):
            f = frozenset((a, b)); wide[f] = wide.get(f, 0) + p
        t = frozenset((i, j, k)); trio[t] = trio.get(t, 0) + p
    return dict(win=win, top2=top2, top3=top3, quin=quin, wide=wide, trio=trio, tri=tri)


def check_sums(d, tag):
    tol = 1e-9
    assert abs(sum(d["win"].values()) - 1) < tol, tag
    assert abs(sum(d["top2"].values()) - 2) < tol, tag
    assert abs(sum(d["top3"].values()) - 3) < tol, tag
    assert abs(sum(d["quin"].values()) - 1) < tol, tag   # 馬連合計1
    assert abs(sum(d["wide"].values()) - 3) < tol, tag   # ワイド合計3
    assert abs(sum(d["trio"].values()) - 1) < tol, tag   # 三連複合計1
    assert abs(sum(d["tri"].values()) - 1) < tol, tag    # 三連単合計1
    assert len(d["quin"]) == 91 and len(d["wide"]) == 91 and len(d["trio"]) == 364 and len(d["tri"]) == 2184


def mc_check(w, n, seed):
    rng = random.Random(seed)
    logw = {h: math.log(w[h]) for h in HORSES}
    cnt_tri, cnt_win = {}, {h: 0 for h in HORSES}
    for _ in range(n):
        g = sorted(HORSES, key=lambda h: -(logw[h] - math.log(-math.log(rng.random()))))
        key = (g[0], g[1], g[2])
        cnt_tri[key] = cnt_tri.get(key, 0) + 1
        cnt_win[g[0]] += 1
    return cnt_tri, cnt_win


def fmt(x, nd=4):
    return f"{x:.{nd}f}"


def main():
    log = []
    P = lambda *a: (log.append(" ".join(str(x) for x in a)), print(*a))
    P("python", sys.version.split()[0], "seed", SEED, "N_MC", N_MC, "temps", TEMPS)
    qodds = load_quinella_odds()
    mwin, mq = load_market()

    D = {}
    for tag, T in TEMPS.items():
        w = strengths(T)
        D[tag] = derive(exact_top3(w))
        check_sums(D[tag], tag)
        P(f"[{tag}] T={T} sums OK: win=1 top2=2 top3=3 quinella=1 wide=3 trio=1 trifecta=1 (exact)")

    # --- MC 検算（基準T） ---
    w16 = strengths(T_BASE)
    cnt_tri, cnt_win = mc_check(w16, N_MC, SEED)
    assert sum(cnt_tri.values()) == N_MC
    mc_q = {}
    for (i, j, k), c in cnt_tri.items():
        f = frozenset((i, j)); mc_q[f] = mc_q.get(f, 0) + c / N_MC
    max_dw = max(abs(cnt_win[h] / N_MC - D["T16_base"]["win"][h]) for h in HORSES)
    max_dq = max(abs(mc_q.get(f, 0) - D["T16_base"]["quin"][f]) for f in D["T16_base"]["quin"])
    P(f"MC check (T16, n={N_MC}, seed={SEED}): max|win diff|={max_dw:.5f}, max|quinella diff|={max_dq:.5f}")
    assert max_dw < 0.005 and max_dq < 0.004

    b, c, a = D["T16_base"], D["T24_cons"], D["T11_aggr"]

    # --- 馬別周辺確率（全14頭） ---
    with open(os.path.join(HERE, "horse_marginals.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["horse_no", "name", "mark", "score", "win_T11", "win_T16", "win_T24", "top2_T16",
                     "top3_T11", "top3_T16", "top3_T24", "market_win_normalized(比較のみ)", "model_div_market_T16", "evidence"])
        for h in HORSES:
            wr.writerow([h, NAMES[h], MARKS.get(h, ""), SCORE[h], fmt(a["win"][h]), fmt(b["win"][h]), fmt(c["win"][h]),
                         fmt(b["top2"][h]), fmt(a["top3"][h]), fmt(b["top3"][h]), fmt(c["top3"][h]),
                         fmt(mwin[h]), f"{b['win'][h] / mwin[h]:.2f}", "EXPERIMENTAL(未校正PL)"])

    def pc(key, kind):
        return min(D[t][kind][key] for t in TEMPS)

    # --- 馬連 21組（A/B） ---
    qrows = []
    for x, y in itertools.combinations(MARKED, 2):
        f = frozenset((x, y)); o = qodds[f]
        grp = "A" if HONMEI in f else "B"
        pb, pcons = b["quin"][f], pc(f, "quin")
        ev_b = pb * o - 1
        ev_drop = pb * o * ODDS_DROP - 1
        ev_rise = pb * o * ODDS_RISE - 1
        ev_c = pcons * o * ODDS_DROP - 1
        ev_t24 = c["quin"][f] * o * ODDS_DROP - 1
        ev_a = a["quin"][f] * o - 1
        if ev_c > 0:
            judge, why = "条件付き", "保守EV>0（3温度最小p×o×0.9）。ただし価格01:30前売り・p未校正のため正式採用不可"
        elif ev_b > 0:
            judge, why = "見送り", "基準EVは正だが保守EV≤0（下振れ・価格下落で消える）"
        else:
            judge, why = "見送り", "基準EV≤0"
        qrows.append(dict(bet="馬連", combo=f"{x}-{y}", group=grp, marks=MARKS[x] + MARKS[y],
                          p_T11=a["quin"][f], p_T16=pb, p_T24=c["quin"][f], p_cons=pcons,
                          market_norm=mq[f], odds=o, obs="2026-10-17 01:30 前売り",
                          be_base=1 / pb, be_cons=1 / pcons, gap=o - 1 / pb,
                          ev_base=ev_b, ev_aggr=ev_a, ev_drop=ev_drop, ev_rise=ev_rise, ev_T24drop=ev_t24, ev_cons=ev_c,
                          judge=judge, why=why, evidence="CONDITIONAL EV（前売り価格×未校正PL確率）"))
    qrows.sort(key=lambda r: (-r["ev_cons"], -r["ev_base"]))
    for i, r in enumerate(qrows, 1):
        r["rank"] = i
    with open(os.path.join(HERE, "quinella_ev.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["rank_by_cons_EV", "bet", "combo", "group", "marks", "p_T11", "p_T16_base", "p_T24", "p_conservative",
                     "market_normalized(比較のみ)", "odds_0130", "observed", "breakeven_1/p_base", "breakeven_1/p_cons",
                     "price_gap_o-1/p", "EV_yen_per100_base", "EVrate_base_%", "EVrate_aggrT11_%", "EVrate_odds-10%_%",
                     "EVrate_odds+10%_%", "EVrate_T24_odds-10%_%", "EVrate_conservative_%", "judge", "reason", "evidence"])
        for r in qrows:
            wr.writerow([r["rank"], r["bet"], r["combo"], r["group"], r["marks"], fmt(r["p_T11"]), fmt(r["p_T16"]), fmt(r["p_T24"]),
                         fmt(r["p_cons"]), fmt(r["market_norm"]), r["odds"], r["obs"], f"{r['be_base']:.1f}", f"{r['be_cons']:.1f}",
                         f"{r['gap']:+.1f}", f"{100 * r['ev_base']:+.1f}", f"{100 * r['ev_base']:+.1f}", f"{100 * r['ev_aggr']:+.1f}",
                         f"{100 * r['ev_drop']:+.1f}", f"{100 * r['ev_rise']:+.1f}", f"{100 * r['ev_T24drop']:+.1f}",
                         f"{100 * r['ev_cons']:+.1f}", r["judge"], r["why"], r["evidence"]])
    P("Quinella 21 (A=%d, B=%d) written" % (sum(r["group"] == "A" for r in qrows), sum(r["group"] == "B" for r in qrows)))

    # --- 参考：馬連全91（印外含む）p と市場比較（候補宇宙外。採否対象ではない） ---
    with open(os.path.join(HERE, "quinella_all91_reference.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["combo", "in_marked7", "p_T16", "p_cons", "odds_0130", "EVrate_base_%", "EVrate_cons_%", "market_normalized(比較のみ)"])
        for fz in sorted(qodds, key=lambda z: sorted(z)):
            x, y = sorted(fz)
            pb, pcons, o = b["quin"][fz], pc(fz, "quin"), qodds[fz]
            wr.writerow([f"{x}-{y}", int(x in MARKS and y in MARKS), fmt(pb, 5), fmt(pcons, 5), o,
                         f"{100 * (pb * o - 1):+.1f}", f"{100 * (pcons * o * ODDS_DROP - 1):+.1f}", fmt(mq[fz], 5)])

    # --- ワイド 21 / 三連複 35 / 三連単 210（価格なし → 必要最低オッズ） ---
    def write_req(fname, kind, combos, label):
        rows = []
        for cmb in combos:
            key = cmb if kind == "tri" else frozenset(cmb)
            pb, pcons = b[kind][key], pc(key, kind)
            grp = "A" if HONMEI in cmb else "B"
            rows.append((cmb, grp, a[kind][key], pb, c[kind][key], pcons))
        rows.sort(key=lambda r: -r[5])
        with open(os.path.join(HERE, fname), "w", encoding="utf-8", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["rank_by_p_cons", "bet", "combo", "group", "marks", "p_T11", "p_T16_base", "p_T24", "p_conservative",
                         "required_min_odds_1/p_base", "required_min_odds_1/p_cons", "required_odds_if_10pct_drop(=1/(p_cons*0.9))",
                         "observed_odds", "judge", "evidence"])
            for i, (cmb, grp, p1, p2, p3, p4) in enumerate(rows, 1):
                sep = "→" if kind == "tri" else "-"
                wr.writerow([i, label, sep.join(map(str, cmb)), grp, "".join(MARKS[h] for h in cmb), fmt(p1, 5), fmt(p2, 5), fmt(p3, 5),
                             fmt(p4, 5), f"{1 / p2:.1f}", f"{1 / p4:.1f}", f"{1 / (p4 * ODDS_DROP):.1f}",
                             "NOT-AVAILABLE", "EV算定保留", "EXPERIMENTAL p（未校正PL）／価格未取得"])
        return rows

    wide_rows = write_req("wide_required_odds.csv", "wide", list(itertools.combinations(MARKED, 2)), "ワイド")
    trio_rows = write_req("trio_required_odds.csv", "trio", list(itertools.combinations(MARKED, 3)), "三連複")
    trif_rows = write_req("trifecta_required_odds.csv", "tri", list(itertools.permutations(MARKED, 3)), "三連単")
    assert len(wide_rows) == 21 and len(trio_rows) == 35 and len(trif_rows) == 210
    for nm, rr in (("wide", wide_rows), ("trio", trio_rows), ("trifecta", trif_rows)):
        P(f"{nm}: n={len(rr)} A={sum(r[1] == 'A' for r in rr)} B={sum(r[1] == 'B' for r in rr)} "
          f"sum p_T16 within marked = {sum(r[3] for r in rr):.4f}")

    # --- 印7頭の被覆率 ---
    for tag in TEMPS:
        cov_q = sum(D[tag]["quin"][frozenset(p)] for p in itertools.combinations(MARKED, 2))
        cov_t = sum(D[tag]["trio"][frozenset(t)] for t in itertools.combinations(MARKED, 3))
        P(f"[{tag}] P(1-2着とも印内)={cov_q:.4f}  P(1-3着すべて印内)={cov_t:.4f}  P(◎3着内)={D[tag]['top3'][HONMEI]:.4f}")

    # --- 購入集合 4案比較（馬連のみ価格あり。100円均等の仮定） ---
    def plan_stats(sel, name, basis):
        n = len(sel)
        if n == 0:
            return dict(plan=name, basis=basis, combos="なし", points=0, invest=0, hon_dep="算出対象外",
                        exp_profit_base=0, exp_profit_cons=0, exp_profit_T24=0, exp_profit_T11=0, roi_base="対象外", roi_cons="対象外",
                        hit_p_base=0, hit_p_cons=0, max_loss=0)
        inv = 100 * n
        e_b = sum(100 * r["ev_base"] for r in sel)
        e_c = sum(100 * r["ev_cons"] for r in sel)
        e_24 = sum(100 * r["ev_T24drop"] for r in sel)
        e_11 = sum(100 * r["ev_aggr"] for r in sel)
        hit_b = sum(r["p_T16"] for r in sel)  # 馬連は互いに排反 → 和が的中確率
        hit_c = sum(r["p_cons"] for r in sel)
        dep = sum(r["group"] == "A" for r in sel)
        return dict(plan=name, basis=basis, combos=" ".join(r["combo"] for r in sel), points=n, invest=inv,
                    hon_dep=f"{dep}/{n}={dep / n:.0%}", exp_profit_base=e_b, exp_profit_cons=e_c, exp_profit_T24=e_24,
                    exp_profit_T11=e_11, roi_base=f"{(inv + e_b) / inv:.3f}", roi_cons=f"{(inv + e_c) / inv:.3f}",
                    hit_p_base=hit_b, hit_p_cons=hit_c, max_loss=inv)

    qual = [r for r in qrows if r["judge"] == "条件付き"]
    byb = sorted(qrows, key=lambda r: -r["ev_base"])
    plans = [
        plan_stats([r for r in qual if r["group"] == "A"][:5], "Aのみ", "保守EV>0の馬連（A群）上位≤5"),
        plan_stats([r for r in qual if r["group"] == "B"][:5], "Bのみ", "保守EV>0の馬連（B群）上位≤5"),
        plan_stats(qual[:5], "A＋B混合", "保守EV>0の馬連（単一ランキング）上位≤5"),
        plan_stats([], "NO BET", "購入なし"),
        plan_stats([r for r in byb if r["group"] == "A"][:5], "参考:A群基準EV上位5", "ゲート無視の参考（採否に使わない）"),
        plan_stats([r for r in byb if r["group"] == "B"][:5], "参考:B群基準EV上位5", "ゲート無視の参考（採否に使わない）"),
        plan_stats(byb[:5], "参考:混合基準EV上位5", "ゲート無視の参考（採否に使わない）"),
    ]
    with open(os.path.join(HERE, "portfolio_compare.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        keys = ["plan", "basis", "combos", "points", "invest", "hon_dep", "exp_profit_base", "exp_profit_cons", "exp_profit_T24",
                "exp_profit_T11", "roi_base", "roi_cons", "hit_p_base", "hit_p_cons", "max_loss"]
        wr.writerow(keys)
        for pl in plans:
            wr.writerow([(f"{pl[k]:+.1f}" if k.startswith("exp_") else (fmt(pl[k]) if k.startswith("hit_") else pl[k])) for k in keys])
    for pl in plans:
        P("PLAN", pl["plan"], pl["combos"], "inv", pl["invest"], "E_base %+.1f" % pl["exp_profit_base"],
          "E_cons %+.1f" % pl["exp_profit_cons"], "hit_base %.4f" % pl["hit_p_base"])

    with open(os.path.join(HERE, "run.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    outs = ["horse_marginals.csv", "quinella_ev.csv", "quinella_all91_reference.csv", "wide_required_odds.csv",
            "trio_required_odds.csv", "trifecta_required_odds.csv", "portfolio_compare.csv"]
    h = hashlib.sha256()
    for o in outs:
        h.update(open(os.path.join(HERE, o), "rb").read())
    msg = "OUTPUT_SHA256 " + h.hexdigest()
    print(msg)
    with open(os.path.join(HERE, "run.log"), "a", encoding="utf-8") as f:
        f.write(msg + "\n")


if __name__ == "__main__":
    main()
