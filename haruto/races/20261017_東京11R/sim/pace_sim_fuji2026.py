# -*- coding: utf-8 -*-
"""
HARUTO Pace / Simulation — 2026-10-17 東京11R 富士S（芝1600m・14頭）
状態: EXPERIMENTAL（未校正・未検証。勝率/馬券的中確率ではない）

入力（すべて発走前に確定した過去走・RT6表のみ。対象レース結果は不使用）
  - input/261017_11R_sennreki1.utf8.csv : 過去走の通過順(通過1〜4)・頭数・芝ダ・距離
  - input/rt6_tables.tsv 表A            : 能力M・能平均・3F（RT6内部指標＝EXPERIMENTAL）

モデル（すべて本担当が作った暫定の仮定。過去データで係数を推定していない）
  1) 序盤位置: 各馬の芝過去走(最大6走)の「最初に記録された通過順」を (順位-1)/(頭数-1) に正規化し、
     新しい走ほど重い加重平均 mu と標準偏差 sd を作る。潜在位置 = mu + sd*N(0,1) を並べ替えて隊列とする。
     調整（仮定）: 枠 +0.015*(馬番-7.5)/6.5、⑬は2000m以上中心の履歴のため +0.12・sd+0.05、
     ⑫②は約28週の休み明けで sd+0.04。
  2) ペースシナリオ: スロー35% / 平均50% / ハイ15% は【仮定】（実測ペース分布ではない）。
     序盤位置の抽選とは独立に抽選する（条件付き連動は未実装）。
  3) 着順感度: perf = 能力z + b_s*(0.5-序盤位置%) + c_s*上がりz + Gumbel(0,1)
     能力z = 0.5*z(能力M)+0.5*z(能平均)、上がりz = -z(RT6 3F)。
     b_s: スロー+0.5/平均+0.1/ハイ-0.5、c_s: スロー0.15/平均0.30/ハイ0.45（すべて仮定）。
     → 出力は「シナリオ感度の頻度」であり、校正済み確率ではない。EV計算に流用禁止。
"""
import csv, json, math, os, random, statistics, sys, hashlib

SEED = 20261017
N_TRIALS = 10000
SCEN = [("スロー", 0.35, 0.5, 0.15), ("平均", 0.50, 0.1, 0.30), ("ハイ", 0.15, -0.5, 0.45)]

BASE = os.path.dirname(os.path.abspath(__file__))
INP = os.path.join(BASE, "..", "input")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_rt6():
    rows = {}
    with open(os.path.join(INP, "rt6_tables.tsv"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    i = lines.index("# 表A: RT一覧（基本表）")
    hdr = lines[i + 2].split("\t")
    for ln in lines[i + 3: i + 17]:
        c = ln.split("\t")
        rec = dict(zip(hdr, c))
        rows[int(rec["馬"])] = {"name": rec["馬名"], "abM": float(c[11]), "abAvg": float(c[13]), "f3": float(c[21])}
    assert len(rows) == 14
    return rows


def load_positions():
    by = {}
    with open(os.path.join(INP, "261017_11R_sennreki1.utf8.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r = {k.strip(): v for k, v in r.items()}
            if r["芝・ダート"] != "芝":
                continue
            ps = [r["通過%d" % k].strip() for k in range(1, 5)]
            ps = [p for p in ps if p]
            if not ps:
                continue
            n = int(r["頭数"])
            by.setdefault(r["馬名"], []).append((r["日付"], int(r["距離"]), (int(ps[0]) - 1) / (n - 1)))
    return by  # 各馬は新しい順に並んでいる（SENREKIの並び）


def z(vals):
    m = statistics.mean(vals); s = statistics.pstdev(vals)
    return [(v - m) / s for v in vals]


def main():
    rt6 = load_rt6()
    pos = load_positions()
    horses = []
    for no in range(1, 15):
        nm = rt6[no]["name"]
        runs = pos[nm][:6]
        w = [0.85 ** k for k in range(len(runs))]
        mu = sum(wi * r[2] for wi, r in zip(w, runs)) / sum(w)
        sd = max(0.12, statistics.pstdev([r[2] for r in runs]) if len(runs) > 1 else 0.2)
        mu += 0.015 * (no - 7.5) / 6.5
        if no == 13:
            mu += 0.12; sd += 0.05
        if no in (2, 12):
            sd += 0.04
        horses.append({"no": no, "name": nm, "mu": mu, "sd": sd, "n_runs": len(runs), **rt6[no]})
    za = z([h["abM"] for h in horses]); zb = z([h["abAvg"] for h in horses]); zf = z([h["f3"] for h in horses])
    for h, a, b, c in zip(horses, za, zb, zf):
        h["ability_z"] = 0.5 * a + 0.5 * b
        h["closing_z"] = -c

    rng = random.Random(SEED)
    N = len(horses)
    sc_count = {s[0]: 0 for s in SCEN}
    lead = {s[0]: [0] * N for s in SCEN}; top3e = {s[0]: [0] * N for s in SCEN}; erank = {s[0]: [0] * N for s in SCEN}
    win = {s[0]: [0] * N for s in SCEN}; top3f = {s[0]: [0] * N for s in SCEN}
    mass_ok = True
    for t in range(N_TRIALS):
        u = rng.random(); acc = 0
        for name, p, b, c in SCEN:
            acc += p
            if u < acc:
                break
        sc_count[name] += 1
        lat = [h["mu"] + h["sd"] * rng.gauss(0, 1) for h in horses]
        order = sorted(range(N), key=lambda i: lat[i])
        epos = [0.0] * N
        for r, i in enumerate(order):
            epos[i] = r / (N - 1); erank[name][i] += r + 1
        lead[name][order[0]] += 1
        for i in order[:3]:
            top3e[name][i] += 1
        perf = []
        for i, h in enumerate(horses):
            g = -math.log(-math.log(rng.random() or 1e-12))
            perf.append(h["ability_z"] + b * (0.5 - epos[i]) + c * h["closing_z"] + g)
        fin = sorted(range(N), key=lambda i: -perf[i])
        if len(set(fin)) != N:
            mass_ok = False
        win[name][fin[0]] += 1
        for i in fin[:3]:
            top3f[name][i] += 1

    def pct(a, d):
        return [round(100 * x / d, 2) if d else None for x in a]

    out = {"seed": SEED, "trials": N_TRIALS, "status": "EXPERIMENTAL（未校正。勝率・馬券的中確率ではない）",
           "scenario_assumed_ratio": {s[0]: s[1] for s in SCEN}, "scenario_drawn": sc_count,
           "input_sha256": {"sennreki1": sha(os.path.join(INP, "261017_11R_sennreki1.utf8.csv")),
                            "rt6_tables": sha(os.path.join(INP, "rt6_tables.tsv"))},
           "horses": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items()} for h in horses],
           "by_scenario": {}, "overall": {}, "mass_check_unique_order": mass_ok}
    for name, *_ in SCEN:
        d = sc_count[name]
        out["by_scenario"][name] = {"n": d, "early_leader_pct": pct(lead[name], d), "early_top3_pct": pct(top3e[name], d),
                                    "early_mean_rank": [round(x / d, 2) for x in erank[name]],
                                    "finish_sens_top1_freq_pct": pct(win[name], d), "finish_sens_top3_freq_pct": pct(top3f[name], d)}
    for key, src in (("early_leader_pct", lead), ("early_top3_pct", top3e), ("finish_sens_top1_freq_pct", win), ("finish_sens_top3_freq_pct", top3f)):
        tot = [sum(src[s[0]][i] for s in SCEN) for i in range(N)]
        out["overall"][key] = pct(tot, N_TRIALS)
    # 質量監査
    assert abs(sum(out["overall"]["early_leader_pct"]) - 100) < 0.1
    assert abs(sum(out["overall"]["early_top3_pct"]) - 300) < 0.1
    assert abs(sum(out["overall"]["finish_sens_top1_freq_pct"]) - 100) < 0.1
    assert abs(sum(out["overall"]["finish_sens_top3_freq_pct"]) - 300) < 0.1
    json.dump(out, open(os.path.join(BASE, "pace_sim_output.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 人が読む表
    print("seed", SEED, "trials", N_TRIALS, "scenario drawn", sc_count, "mass_ok", mass_ok)
    print("no name mu sd abZ clZ | lead% top3e% | S:lead S:top1sens S:top3sens | M:top1 M:top3 | H:top1 H:top3 | ALL top1sens top3sens")
    for i, h in enumerate(horses):
        bs = out["by_scenario"]
        print(h["no"], h["name"], round(h["mu"], 3), round(h["sd"], 3), round(h["ability_z"], 2), round(h["closing_z"], 2), "|",
              out["overall"]["early_leader_pct"][i], out["overall"]["early_top3_pct"][i], "|",
              bs["スロー"]["finish_sens_top1_freq_pct"][i], bs["スロー"]["finish_sens_top3_freq_pct"][i], "|",
              bs["平均"]["finish_sens_top1_freq_pct"][i], bs["平均"]["finish_sens_top3_freq_pct"][i], "|",
              bs["ハイ"]["finish_sens_top1_freq_pct"][i], bs["ハイ"]["finish_sens_top3_freq_pct"][i], "|",
              out["overall"]["finish_sens_top1_freq_pct"][i], out["overall"]["finish_sens_top3_freq_pct"][i])


if __name__ == "__main__":
    main()
