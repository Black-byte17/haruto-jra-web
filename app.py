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
    omega    = int(horse.get("omega_idx", 0))
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

    # スコア計算: Ω指数未取得(=0)のときはオッズ100%で代替
    if omega > 0:
        ability_score = _omega_ability(omega) * 0.7 + _odds_score(odds) * 0.3
        tjra = _tjra(omega)
    else:
        ability_score = _odds_score(odds)
        tjra = 0.0
    jockey_score  = _jockey_base(keigen)
    kinryo_corr   = _kinryo_corr(sex, kinryo, distance, grade)
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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

# ──────────────────────────────────────────────
# レース一覧取得 (keibalab.jp)
# ──────────────────────────────────────────────

def get_race_list(target_date: date | None = None) -> dict:
    """当日のレース一覧取得"""
    if target_date is None:
        target_date = date.today()
    ds = target_date.strftime("%Y%m%d")
    # 正しいURL: /db/race/?kaisai_date=YYYYMMDD
    url = f"{BASE}/db/race/?kaisai_date={ds}"
    soup = _get(url)
    venues: dict[str, dict] = {}

    if soup:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/db/race/" not in href:
                continue
            # レースURL形式: /db/race/YYYYMMDDVVNN/ (正確に12桁)
            m = re.search(r"/db/race/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})/$", href)
            if not m:
                # 末尾スラッシュなしも試す
                m = re.search(r"/db/race/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(?:/|$)", href)
            if not m:
                continue
            year, month, day, venue_code, race_no_s = m.groups()
            race_no = int(race_no_s)
            if venue_code not in VENUE_MAP or race_no <= 0:
                continue
            venue_name = VENUE_MAP[venue_code]
            full_url = (BASE + href) if href.startswith("/") else href

            if venue_code not in venues:
                venues[venue_code] = {"code": venue_code, "name": venue_name, "races": []}
            existing = [r["race_no"] for r in venues[venue_code]["races"]]
            if race_no not in existing:
                venues[venue_code]["races"].append({
                    "race_no": race_no,
                    "href":    href,
                    "url":     full_url,
                })

    result = list(venues.values())
    for v in result:
        v["races"].sort(key=lambda r: r["race_no"])
    print(f"[keibalab] {ds}: {len(result)}会場")
    return {"date": ds, "venues": result}


# ──────────────────────────────────────────────
# レース詳細（出馬表）取得
# ──────────────────────────────────────────────

def get_race_detail(race_url: str) -> dict | None:
    """レース詳細（出馬表 or 結果表）取得"""
    soup = _get(race_url)
    if not soup:
        return None

    race = {"url": race_url, "horses": [], "distance": 1600,
            "course_type": "芝", "condition": "良", "grade": ""}

    # ── レース情報 ──
    for sel in [".raceaboutbox", ".racedatawrap", ".race-info", ".raceinfo",
                ".mainrace_data", ".RaceData01"]:
        info_el = soup.select_one(sel)
        if info_el:
            info_text = info_el.get_text(" ", strip=True)
            m_dist = re.search(r"(\d{3,4})m", info_text)
            if m_dist:
                race["distance"] = int(m_dist.group(1))
            if "ダ" in info_text or "ダート" in info_text:
                race["course_type"] = "ダ"
            for g in ["GIII","GII","GI"]:
                if g in info_text:
                    race["grade"] = g
                    break
            for c in ["良","稍重","重","不良"]:
                if c in info_text:
                    race["condition"] = c
                    break
            break

    # ── テーブルを探してヘッダーで列構造を判定 ──
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # ヘッダー行の取得
        header_cells = rows[0].find_all(["th","td"])
        headers = [c.get_text(" ", strip=True) for c in header_cells]

        # 列インデックスの決定
        # keibalab resulttable: 着順|枠番|馬番|馬名|性齢|斤量|騎手|人気|...
        # keibalab shutuba:     枠番|馬番|馬名|性齢|斤量|騎手|...  または 馬番|馬名|...
        if any("着" in h for h in headers[:2]):
            # 結果テーブル
            i_uma, i_name, i_sex, i_kin, i_joc, i_pop = 2, 3, 4, 5, 6, 7
        elif any("枠" in h for h in headers[:2]):
            # 枠番が先頭にある出馬表
            i_uma, i_name, i_sex, i_kin, i_joc, i_pop = 1, 2, 3, 4, 5, 7
        else:
            # 馬番が先頭の出馬表
            i_uma, i_name, i_sex, i_kin, i_joc, i_pop = 0, 1, 2, 3, 4, 6

        for row in rows[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < max(i_uma, i_name, i_joc) + 1:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]

            uma_no = _si(texts[i_uma]) if i_uma < len(texts) else 0
            if not (1 <= uma_no <= 18):
                continue
            name = texts[i_name] if i_name < len(texts) else ""
            if not name or len(name) < 2:
                continue

            sex_raw = texts[i_sex] if i_sex < len(texts) else "牡"
            sex = sex_raw[:1] if sex_raw else "牡"

            kinryo = _sf(texts[i_kin]) if i_kin < len(texts) else 57.0
            if not (49 <= kinryo <= 62):
                kinryo = 57.0

            jockey = texts[i_joc] if i_joc < len(texts) else ""
            ninki  = _si(texts[i_pop]) if i_pop < len(texts) else 0

            # オッズ（表中の小数値を探す）
            odds = 10.0
            for t in reversed(texts):
                v = _sf(t)
                if 1.0 <= v <= 999.9 and "." in t:
                    odds = v
                    break

            # Ω指数（出馬表ページのみ存在。結果ページは0=未取得）
            omega = 0
            for t in texts:
                m = re.search(r"Ω[:\s]*(\d+)", t)
                if m:
                    omega = int(m.group(1))
                    break

            race["horses"].append({
                "uma_no":      uma_no,
                "name":        name,
                "sex":         sex,
                "kinryo":      kinryo,
                "jockey":      jockey,
                "keigen":      "",
                "odds":        odds,
                "ninki":       ninki,
                "kyakushitsu": "",
                "omega_idx":   omega,
                "compi_idx":   0,
                "sire_name":   "",
                "alpha":       "",
            })

        if race["horses"]:
            break

    return race if race["horses"] else None


# ──────────────────────────────────────────────
# NAR（地方競馬）スクレイパー  keiba.go.jp
# ──────────────────────────────────────────────

NAR_BASE = "https://www.keiba.go.jp"

NAR_VENUE_MAP = {
    "10": "帯広", "11": "水沢", "12": "盛岡",
    "20": "大井", "21": "川崎", "22": "金沢",
    "23": "笠松", "24": "名古屋", "25": "姫路",
    "27": "園田", "30": "高松", "31": "高知",
    "32": "佐賀", "35": "宮崎",
}

NAR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "https://www.keiba.go.jp/",
}


def _nar_get(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=NAR_HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[NAR scraper] 失敗: {url} → {e}")
        return None


def get_nar_race_list(target_date: date | None = None) -> dict:
    """地方競馬レース一覧取得（keiba.go.jp）"""
    if target_date is None:
        target_date = date.today()
    ds_display = target_date.strftime("%Y%m%d")
    ds_encoded = target_date.strftime("%Y%%2f%m%%2f%d")   # URL用: 2026%2f03%2f25
    ds_slash   = target_date.strftime("%Y/%m/%d")          # 比較用: 2026/03/25

    # TodayRaceInfoTop から当日の会場リンクを収集
    top_url = f"{NAR_BASE}/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop"
    soup = _nar_get(top_url)
    venue_codes: list[str] = []

    if soup:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(
                r"RaceList\?k_raceDate=(\d{4}%2[Ff]\d{2}%2[Ff]\d{2})&k_babaCode=(\d+)",
                href
            )
            if not m:
                continue
            date_raw = m.group(1).replace("%2f", "/").replace("%2F", "/")
            code = m.group(2)
            if date_raw == ds_slash and code not in venue_codes:
                venue_codes.append(code)

    venues: list[dict] = []
    for code in venue_codes:
        list_url = (
            f"{NAR_BASE}/KeibaWeb/TodayRaceInfo/RaceList"
            f"?k_raceDate={ds_encoded}&k_babaCode={code}"
        )
        list_soup = _nar_get(list_url)
        if not list_soup:
            continue

        races: list[dict] = []
        for a in list_soup.find_all("a", href=True):
            href = a["href"]
            m2 = re.search(r"DebaTable\?.*?k_raceNo=(\d+).*?k_babaCode=(\d+)", href)
            if not m2:
                m2 = re.search(r"DebaTable\?.*?k_babaCode=(\d+).*?k_raceNo=(\d+)", href)
                if not m2:
                    continue
                rno, bc = int(m2.group(2)), m2.group(1)
            else:
                rno, bc = int(m2.group(1)), m2.group(2)

            # フルURL生成
            # href例: "../TodayRaceInfo/DebaTable?..." → /KeibaWeb/TodayRaceInfo/DebaTable?...
            if href.startswith("../"):
                full = f"{NAR_BASE}/KeibaWeb/{href[3:]}"
            elif href.startswith("/"):
                full = NAR_BASE + href
            else:
                full = f"{NAR_BASE}/KeibaWeb/TodayRaceInfo/{href}"

            if rno not in [r["race_no"] for r in races]:
                races.append({"race_no": rno, "url": full})

        if races:
            races.sort(key=lambda r: r["race_no"])
            venues.append({
                "code":  code,
                "name":  NAR_VENUE_MAP.get(code, f"会場{code}"),
                "races": races,
            })

    print(f"[NAR] {ds_display}: {len(venues)}会場")
    return {"date": ds_display, "venues": venues}


def get_nar_race_detail(race_url: str) -> dict | None:
    """地方競馬出馬表取得・パース"""
    soup = _nar_get(race_url)
    if not soup:
        return None

    race = {
        "url":         race_url,
        "horses":      [],
        "distance":    1600,
        "course_type": "ダ",
        "condition":   "良",
        "grade":       "",
        "is_nar":      True,
    }

    # レース情報（タイトル・距離・馬場）
    for sel in ["h2", "h3", ".raceTitle", ".race_name"]:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            m_d = re.search(r"(\d{3,4})m", txt)
            if m_d:
                race["distance"] = int(m_d.group(1))
            if "芝" in txt:
                race["course_type"] = "芝"
            for c in ["良", "稍重", "重", "不良"]:
                if c in txt:
                    race["condition"] = c
                    break
            for g in ["JpnIII", "JpnII", "JpnI"]:
                if g in txt:
                    race["grade"] = g
                    break
            break

    # 出馬表テーブル（Table 0）
    main_tbl = soup.find("table")
    if not main_tbl:
        return None

    rows = main_tbl.find_all("tr")
    i = 0
    while i < len(rows):
        cells = rows[i].find_all(["td", "th"])
        # 馬データ行 = セル数 ≥ 10 かつ先頭2セルが枠番・馬番
        if len(cells) >= 10:
            texts = [c.get_text(" ", strip=True) for c in cells]
            # 枠番(0)・馬番(1)が1桁数字か確認
            wakuban = _si(texts[0])
            umano   = _si(texts[1])
            if 1 <= wakuban <= 8 and 1 <= umano <= 20:
                # 馬名
                name = texts[2].strip()
                # 騎手（テキスト中の最初の名前部分）
                jockey_raw = texts[3] if len(texts) > 3 else ""
                jockey = re.split(r"\s|　|\n", jockey_raw.strip())[0]
                # オッズ・人気: "3.0 (3人気)" or "3.0\n(3人気)"
                odds_raw = texts[4] if len(texts) > 4 else ""
                odds, ninki = 10.0, 0
                m_op = re.search(r"([\d.]+)\s*[(\s（]*(\d+)人気", odds_raw)
                if m_op:
                    odds  = _sf(m_op.group(1))
                    ninki = int(m_op.group(2))
                else:
                    m_odds = re.search(r"([\d.]+)", odds_raw)
                    if m_odds:
                        odds = _sf(m_odds.group(1))

                # 性齢・斤量：後続行から探す
                sex, kinryo = "牡", 57.0
                for j in range(i + 1, min(i + 12, len(rows))):
                    nc = rows[j].find_all(["td", "th"])
                    if not nc:
                        continue
                    nt = [c.get_text(" ", strip=True) for c in nc]
                    if re.match(r"^[牡牝セ去]\d", nt[0]):
                        sex = nt[0][0]
                        # 斤量は "56.0 2-3-0-0" 形式
                        for t in nt:
                            km = re.match(r"^([\d]{2}\.[\d])", t.strip())
                            if km:
                                v = float(km.group(1))
                                if 49.0 <= v <= 65.0:
                                    kinryo = v
                                    break
                        break

                if name and len(name) >= 2:
                    race["horses"].append({
                        "uma_no":      umano,
                        "name":        name,
                        "sex":         sex,
                        "kinryo":      kinryo,
                        "jockey":      jockey,
                        "keigen":      "",
                        "odds":        odds,
                        "ninki":       ninki,
                        "kyakushitsu": "",
                        "omega_idx":   0,   # NAR はΩ指数なし
                        "compi_idx":   0,
                        "sire_name":   "",
                        "alpha":       "",
                    })
        i += 1

    return race if race["horses"] else None


# ──────────────────────────────────────────────
# NAR スコア計算（Ω指数なし版）
# ──────────────────────────────────────────────

def calc_nar_score(horse: dict, race: dict) -> dict:
    """NAR用HARUTOスコア（Ω指数なし・オッズ主体）"""
    compi   = int(horse.get("compi_idx", 0))
    odds    = float(horse.get("odds", 10.0))
    kinryo  = float(horse.get("kinryo", 57.0))
    sex     = horse.get("sex", "牡")
    keigen  = horse.get("keigen", "")

    distance    = int(race.get("distance", 1600))
    grade       = race.get("grade", "")
    course_type = race.get("course_type", "ダ")
    condition   = race.get("condition", "良")

    # NAR は人気（オッズ）をそのまま能力スコアとして使用
    ability_score = _odds_score(odds)
    jockey_score  = _jockey_base(keigen)
    kinryo_corr   = _kinryo_corr(sex, kinryo, distance, grade)
    compi_bonus   = _compi_bonus(compi)
    # ダート補正（NAR は基本ダート）
    dirt_bonus = 0.5 if course_type == "ダ" and condition in ("重", "不良") else 0.0

    total = (
        ability_score * 0.8 +
        jockey_score  * 0.2 +
        kinryo_corr   +
        compi_bonus   +
        dirt_bonus
    )

    elim = _elim_level(horse)
    if elim >= 2:
        total -= 5.0

    return {
        "total_score": round(total, 2),
        "ability":     round(ability_score, 2),
        "jockey":      round(jockey_score, 2),
        "kinryo_corr": round(kinryo_corr, 3),
        "compi_bonus": round(compi_bonus, 2),
        "elim_level":  elim,
    }


# ──────────────────────────────────────────────
# Flask ルーティング
# ──────────────────────────────────────────────

@app.route("/")
def top_page():
    return render_template("top.html")

@app.route("/jra")
def jra_page():
    return render_template("jra.html")

@app.route("/nar")
def nar_page():
    return render_template("nar.html")

# ── JRA API ──

@app.route("/api/races")
def api_races():
    """JRA レース一覧"""
    ds = request.args.get("date")
    try:
        td = datetime.strptime(ds, "%Y%m%d").date() if ds else date.today()
    except ValueError:
        td = date.today()
    data = get_race_list(td)
    if not data.get("venues"):
        data["message"] = "この日のJRAレースが見つかりません（JRAは土日祝のみ開催）"
    return jsonify(data)


@app.route("/api/predict")
def api_predict():
    """JRA 予想実行"""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url パラメータが必要です"}), 400
    race = get_race_detail(url)
    if not race:
        return jsonify({"error": "データ取得失敗（keibalab.jp）"}), 500

    horses_scored = []
    for h in race["horses"]:
        sc = calc_score(h, race)
        h.update(sc)
        horses_scored.append(h)

    return jsonify({
        "race":   {k: v for k, v in race.items() if k != "horses"},
        "horses": assign_marks(horses_scored),
    })


@app.route("/api/debug")
def api_debug():
    """JRA スクレイパーデバッグ"""
    ds = request.args.get("date", date.today().strftime("%Y%m%d"))
    url = f"{BASE}/db/race/?kaisai_date={ds}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        links = re.findall(r'href="(/db/race/\d{12}/?)"', r.text)
        unique = list(dict.fromkeys(links))[:30]
        return jsonify({"url": url, "status": r.status_code,
                        "race_links_found": unique, "count": len(unique)})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── NAR API ──

@app.route("/api/nar/races")
def api_nar_races():
    """NAR レース一覧（keiba.go.jp）"""
    ds = request.args.get("date")
    try:
        td = datetime.strptime(ds, "%Y%m%d").date() if ds else date.today()
    except ValueError:
        td = date.today()
    data = get_nar_race_list(td)
    if not data.get("venues"):
        data["message"] = "この日の地方競馬レースが見つかりません（本日以外は取得できない場合があります）"
    return jsonify(data)


@app.route("/api/nar/predict")
def api_nar_predict():
    """NAR 予想実行"""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url パラメータが必要です"}), 400
    race = get_nar_race_detail(url)
    if not race:
        return jsonify({"error": "データ取得失敗（keiba.go.jp）"}), 500

    horses_scored = []
    for h in race["horses"]:
        sc = calc_nar_score(h, race)
        h.update(sc)
        horses_scored.append(h)

    return jsonify({
        "race":   {k: v for k, v in race.items() if k != "horses"},
        "horses": assign_marks(horses_scored),
    })


@app.route("/api/nar/debug")
def api_nar_debug():
    """NAR スクレイパーデバッグ"""
    ds = request.args.get("date", date.today().strftime("%Y%m%d"))
    td = datetime.strptime(ds, "%Y%m%d").date()
    ds_slash = td.strftime("%Y/%m/%d")
    top_url = f"{NAR_BASE}/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop"
    try:
        r = requests.get(top_url, headers=NAR_HEADERS, timeout=15)
        links = re.findall(
            r"RaceList\?k_raceDate=(\d{4}%2[Ff]\d{2}%2[Ff]\d{2})&k_babaCode=(\d+)",
            r.text
        )
        filtered = [(d.replace("%2f","/").replace("%2F","/"), c)
                    for d, c in links if d.replace("%2f","/").replace("%2F","/") == ds_slash]
        return jsonify({
            "top_url": top_url,
            "status": r.status_code,
            "target_date": ds_slash,
            "venues_found": list(dict.fromkeys([c for _, c in filtered])),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "4.1.0",
                    "routes": ["/", "/jra", "/nar"]})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
