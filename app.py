"""
app.py — HARUTO Web v4.1.0
Flask Web サーバー
スマホブラウザから URL 一発でアクセス可能

起動: python app.py
"""

from __future__ import annotations
import math
import re
import json
import concurrent.futures
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ──────────────────────────────────────────────
# インライン HARUTOエンジン（依存ゼロ版）
# ──────────────────────────────────────────────

DISTANCE_KINRYO_COEFF = [(1200, 0.8), (1800, 1.0), (2400, 1.0), (3000, 1.2), (9999, 1.5)]
GRADE_BASE_KINRYO = {
    "GI":   {"牡": 58.0, "牝": 56.0, "セ": 58.0},
    "GII":  {"牡": 57.0, "牝": 55.0, "セ": 57.0},
    "GIII": {"牡": 56.0, "牝": 54.0, "セ": 56.0},
    "":     {"牡": 57.0, "牝": 55.0, "セ": 57.0},
}
OMEGA_TO_TJRA = [(100,2.0),(90,1.5),(75,1.0),(60,0.5),(45,0.0),(35,-0.5),(25,-1.0),(0,-1.5)]

SENKO_BIAS = {"前有利","先行有利","senkou"}
OSHI_BIAS  = {"後有利","差し有利","追込有利"}

MARKS = ["◎","○","▲","△","△","×","×","×"]


def _distance_coeff(d: int) -> float:
    for dmax, c in DISTANCE_KINRYO_COEFF:
        if d <= dmax:
            return c
    return 1.5

def _kinryo_corr(sex: str, kinryo: float, distance: int, grade: str) -> float:
    base = GRADE_BASE_KINRYO.get(grade, GRADE_BASE_KINRYO[""]).get(sex, 57.0)
    return round((base - kinryo) * 0.5 * _distance_coeff(distance), 3)

def _tjra(omega: int) -> float:
    for thr, v in OMEGA_TO_TJRA:
        if omega >= thr:
            return v
    return -1.5

def _odds_score(odds: float) -> float:
    if odds <= 0:
        return 50.0
    return max(10.0, round(100.0 - 20.0 * math.log10(max(odds, 1.0)), 2))

def _jockey_base(keigen: str) -> float:
    base = 60.0
    if keigen == "▲": base += 5.0 - 8.0
    elif keigen == "△": base += 3.0 - 5.0
    elif keigen == "☆": base += 7.0 - 10.0
    return base

def _w_factor(course_type: str, condition: str, bias_data: dict | None) -> float:
    if bias_data:
        key = "turf_bias" if course_type == "芝" else "dirt_bias"
        tend = bias_data.get(key, {}).get("tendency", "")
        if tend in SENKO_BIAS: return 1.0
        if tend in OSHI_BIAS:  return -0.5
    if course_type == "芝" and condition in ("良","稍重"):
        return 0.5
    if course_type == "ダ" and condition in ("重","不良"):
        return 0.5
    return 0.0

def _kyakushitsu_factor(kyaku: str, bias_tend: str) -> float:
    if not kyaku or not bias_tend: return 0.0
    front = any(k in kyaku for k in ["逃","先"])
    back  = any(k in kyaku for k in ["差","追"])
    if bias_tend in SENKO_BIAS and front: return 1.5
    if bias_tend in OSHI_BIAS and back:   return 1.5
    if bias_tend in SENKO_BIAS and back:  return -0.5
    if bias_tend in OSHI_BIAS and front:  return -0.5
    return 0.0

def _elim_level(horse: dict) -> int:
    """消し判定: 0=正常 1=L1注意 2=L2消し 3=L3強消し"""
    lv = 0
    if horse.get("連闘", False): lv = max(lv, 2)
    if horse.get("長期休養", False): lv = max(lv, 1)
    return lv

def calc_score(horse: dict, race: dict) -> dict:
    """HARUTOスコア計算。horse / race の dict を受け取りスコアを返す。"""
    omega    = int(horse.get("omega_idx", 50))
    compi    = int(horse.get("compi_idx", 0))
    odds     = float(horse.get("odds", 10.0))
    kinryo   = float(horse.get("kinryo", 57.0))
    sex      = horse.get("sex", "牡")
    keigen   = horse.get("keigen", "")
    kyaku    = horse.get("kyakushitsu", "")

    distance    = int(race.get("distance", 1600))
    grade       = race.get("grade", "")
    course_type = race.get("course_type", "芝")
    condition   = race.get("condition", "良")
    bias_data   = race.get("bias_data", None)
    bias_tend   = (bias_data or {}).get(
        "turf_bias" if course_type == "芝" else "dirt_bias", {}
    ).get("tendency", "")

    # スコア計算
    ability_score = _omega_ability(omega) * 0.7 + _odds_score(odds) * 0.3
    jockey_score  = _jockey_base(keigen)
    kinryo_corr   = _kinryo_corr(sex, kinryo, distance, grade)
    tjra          = _tjra(omega)
    w_fac         = _w_factor(course_type, condition, bias_data)
    kyaku_fac     = _kyakushitsu_factor(kyaku, bias_tend)
    compi_bonus   = _compi_bonus(compi)

    total = (
        ability_score * 0.7 +
        jockey_score  * 0.3 +
        kinryo_corr   +
        tjra          +
        w_fac         +
        kyaku_fac     +
        compi_bonus
    )

    elim = _elim_level(horse)
    if elim >= 2:
        total -= 5.0

    return {
        "total_score":  round(total, 2),
        "ability":      round(ability_score, 2),
        "jockey":       round(jockey_score, 2),
        "kinryo_corr":  round(kinryo_corr, 3),
        "tjra":         round(tjra, 2),
        "w_factor":     round(w_fac, 2),
        "compi_bonus":  round(compi_bonus, 2),
        "elim_level":   elim,
    }

def _omega_ability(omega: int) -> float:
    return float(omega)

def _compi_bonus(compi: int) -> float:
    """日刊コンビ指数補正（0〜+1.5）"""
    if compi >= 90: return 1.5
    if compi >= 80: return 1.0
    if compi >= 70: return 0.5
    if compi >= 60: return 0.0
    if compi > 0:   return -0.5
    return 0.0

def assign_marks(horses_scored: list[dict]) -> list[dict]:
    """スコア順に予想印を割り当てる"""
    sorted_h = sorted(horses_scored, key=lambda h: h["total_score"], reverse=True)
    for i, h in enumerate(sorted_h):
        h["mark"] = MARKS[i] if i < len(MARKS) else ""
    return sorted_h


# ──────────────────────────────────────────────
# スクレイパー（keibalab.jp 公開ページ）
# ──────────────────────────────────────────────

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}
BASE = "https://www.keibalab.jp"

VENUE_MAP = {
    "01":"札幌","02":"函館","03":"福島","04":"新潟",
    "05":"東京","06":"中山","07":"中京","08":"京都",
    "09":"阪神","10":"小倉",
}

def _get(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[scraper] 失敗: {url} → {e}")
        return None

def _sf(s, d=0.0):
    try: return float(re.sub(r"[^\d.\-]","",str(s)) or str(d))
    except: return d

def _si(s, d=0):
    try: return int(re.sub(r"[^\d]","",str(s)) or str(d))
    except: return d

def get_race_list(target_date: date | None = None) -> dict:
    """当日のレース一覧取得"""
    if target_date is None:
        target_date = date.today()
    ds = target_date.strftime("%Y%m%d")
    url = f"{BASE}/race/list/{ds}/"
    soup = _get(url)
    venues = []
    if soup:
        for a in soup.select("a[href*='/race/']"):
            href = a.get("href","")
            m = re.search(r"/race/(\d{2})(\d{4})(\d{2})(\d{2})/", href)
            if not m: continue
            venue_code = m.group(1)
            race_no    = _si(m.group(4))
            venue_name = VENUE_MAP.get(venue_code, venue_code)
            # 既存会場に追加
            found = next((v for v in venues if v["code"]==venue_code), None)
            if not found:
                found = {"code": venue_code, "name": venue_name, "races": []}
                venues.append(found)
            if race_no not in [r["race_no"] for r in found["races"]]:
                found["races"].append({
                    "race_no": race_no,
                    "href":    href,
                    "url":     BASE + href,
                })
        for v in venues:
            v["races"].sort(key=lambda r: r["race_no"])
    return {"date": ds, "venues": venues}

def get_race_detail(race_url: str) -> dict | None:
    """レース詳細（出馬表）取得"""
    soup = _get(race_url)
    if not soup:
        return None

    race = {"url": race_url, "horses": [], "distance": 1600,
            "course_type": "芝", "condition": "良", "grade": ""}

    # レース情報
    info_el = soup.select_one(".race-info, .raceinfo, h1.race-name, .race_header")
    if info_el:
        info_text = info_el.get_text(" ", strip=True)
        m_dist = re.search(r"(\d{3,4})m", info_text)
        if m_dist:
            race["distance"] = int(m_dist.group(1))
        if "ダ" in info_text or "ダート" in info_text:
            race["course_type"] = "ダ"
        for g in ["GI","GII","GIII"]:
            if g in info_text:
                race["grade"] = g
                break
        for c in ["良","稍重","重","不良"]:
            if c in info_text:
                race["condition"] = c
                break

    # 出馬表
    for row in soup.select("table.shutuba tr, table.race-table tr, tr.horse-row"):
        cells = row.find_all(["td","th"])
        if len(cells) < 5:
            continue
        texts = [c.get_text(" ",strip=True) for c in cells]
        uma_no = _si(texts[0])
        if uma_no == 0:
            continue

        horse = {
            "uma_no":      uma_no,
            "name":        texts[3] if len(texts) > 3 else "?",
            "sex":         texts[4][:1] if len(texts) > 4 else "牡",
            "kinryo":      _sf(texts[5]) if len(texts) > 5 else 57.0,
            "jockey":      texts[6] if len(texts) > 6 else "",
            "keigen":      "",
            "odds":        _sf(texts[-2]) if len(texts) > 8 else 10.0,
            "ninki":       _si(texts[-1]) if len(texts) > 8 else 0,
            "kyakushitsu": "",
            "omega_idx":   0,
            "compi_idx":   0,
            "sire_name":   "",
            "alpha":       "",
        }

        # Ω指数（keibalab独自列）
        for t in texts:
            m = re.search(r"Ω[:\s]*(\d+)", t)
            if m:
                horse["omega_idx"] = int(m.group(1))
                break

        race["horses"].append(horse)

    return race if race["horses"] else None


# ──────────────────────────────────────────────
# Flask ルーティング
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/races")
def api_races():
    """当日または指定日のレース一覧"""
    ds = request.args.get("date")
    try:
        td = datetime.strptime(ds, "%Y%m%d").date() if ds else date.today()
    except ValueError:
        td = date.today()
    data = get_race_list(td)
    return jsonify(data)

@app.route("/api/predict")
def api_predict():
    """予想実行 → スコアテーブル返却"""
    url = request.args.get("url","").strip()
    if not url:
        return jsonify({"error": "url パラメータが必要です"}), 400

    race = get_race_detail(url)
    if not race:
        return jsonify({"error": "データ取得失敗"}), 500

    # スコア計算
    horses_scored = []
    for h in race["horses"]:
        sc = calc_score(h, race)
        h.update(sc)
        horses_scored.append(h)

    ranked = assign_marks(horses_scored)

    return jsonify({
        "race":   {k: v for k, v in race.items() if k != "horses"},
        "horses": ranked,
    })

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "4.1.0"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
