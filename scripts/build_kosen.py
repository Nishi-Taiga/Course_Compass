#!/usr/bin/env python3
"""都立産業技術高等専門学校（産技高専）のデータを作る。

    python3 scripts/build_kosen.py

出力:
    data/seed/extra_schools.csv        マスタに足す学校（品川・荒川の2キャンパス）
    data/seed/extra_school_clubs.csv   その部活動

## なぜ別ファイルなのか

産技高専は**都教委の学校一覧に載らない**。設置者が東京都教育委員会ではなく
東京都公立大学法人だからで、schools_master.csv（都教委CSVから生成）には
永久に現れない。schools_master.csv に直接書き足すと build_school_master.py を
流すたびに消えるので、別ファイルにして build_seed_sql.py で合流させる。

## 学校番号

都教委の番号が無いので採番する。都教委の6桁（4xxxxx）と衝突せず、
一目で「都教委由来ではない」と分かるよう 99xxxx を使う。

## キャンパスを2件に分ける理由

品川区と荒川区で、通学時間がまったく違う。1件にまとめると、
どちらのキャンパスに通うのか分からないまま所要時間を出すことになる。
部活動もキャンパスごとに違う（サイトが2列の表で分けている）。

## 入試の扱い

⚠️ 目安点（target_score）は入れない。産技高専の学力選抜は
   学力検査3教科350点＋調査書300点の650点満点で、都立高校の1020点満点
   （当日500×1.4＋換算内申300＋ESAT-J20）とは満点も配点も違う。
   同じ目安点を当てると5教科ぶんの実力を要求していないのに過大評価になる。
   点数では判定せず、その理由を画面に出す（selection_type = kosen）。
"""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_school_clubs import Crawler  # noqa: E402
from parse_clubs import decode_html, strip_noise, text_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
OUT_SCHOOLS = SEED / "extra_schools.csv"
OUT_CLUBS = SEED / "extra_school_clubs.csv"

BASE = "https://www.metro-cit.ac.jp"
ACCESS_URL = f"{BASE}/information/access.html"
CLUB_URL = f"{BASE}/student/club.html"
GSI = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="

SOURCE = "東京都立産業技術高等専門学校 公式サイト"
SOURCE_COORD = "国土地理院 地名検索API（住所から取得）"

CAMPUSES = [
    {
        "school_number": "990001",
        "name": "産業技術高専（品川）",
        "official": "東京都立産業技術高等専門学校 品川キャンパス",
        "ward": "品川区",
        "address": "東大井1-10-40",
        "full_address": "東京都品川区東大井1-10-40",
        "key": "shinagawa",
        "col": 0,
    },
    {
        "school_number": "990002",
        "name": "産業技術高専（荒川）",
        "official": "東京都立産業技術高等専門学校 荒川キャンパス",
        "ward": "荒川区",
        "address": "南千住8-17-1",
        "full_address": "東京都荒川区南千住8-17-1",
        "key": "arakawa",
        "col": 1,
    },
]

# 本科の学科。両キャンパスとも「ものづくり工学科」で、コースが分かれている。
DEPARTMENTS = "工"          # schools.departments は都教委の1文字コードに合わせる
DEPARTMENT_NOTE = "ものづくり工学科（5年制）"


def geocode(crawler: Crawler, address: str) -> tuple[float, float]:
    status, body = crawler.get(GSI + urllib.parse.quote(address))
    if status != 200:
        sys.exit(f"ジオコーディング失敗: HTTP {status}")
    hits = json.loads(body.decode("utf-8"))
    if not hits:
        sys.exit(f"住所が見つかりません: {address}")
    lon, lat = hits[0]["geometry"]["coordinates"]
    return lat, lon


# 「品川シーサイド駅 B出口から徒歩3分」「鮫洲駅 徒歩 9分」の両方を拾う
STATION_RE = re.compile(r"([^\s　、。・]{2,10}?)駅[^。]{0,12}?徒歩\s*(?:約)?\s*(\d{1,2})\s*分")


def parse_access(text: str) -> dict[str, list[tuple[str, int]]]:
    """アクセスページから、キャンパスごとの（駅, 徒歩分）を拾う。

    ページは「■品川キャンパス … ■荒川キャンパス …」の順に並んでいるので、
    見出しで切ってから、それぞれの範囲だけを見る。
    """
    out: dict[str, list[tuple[str, int]]] = {}
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"[■◆]?(品川|荒川)キャンパス", text)]
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        key = "shinagawa" if name == "品川" else "arakawa"
        if key in out:
            continue                      # 最初に現れた節だけを使う（ナビの重複を避ける）
        seen: dict[str, int] = {}
        for st, mins in STATION_RE.findall(text[pos:end]):
            st = st.strip()
            if st and (st not in seen or seen[st] > int(mins)):
                seen[st] = int(mins)
        if seen:
            out[key] = sorted(seen.items(), key=lambda kv: kv[1])
    return out


def parse_clubs_by_campus(html: str) -> dict[str, list[tuple[str, str]]]:
    """部活動ページの2列テーブルから、キャンパスごとの部活を拾う。

    表は「品川キャンパス | 荒川キャンパス」の2列で、タブで運動系/文化系/技術系に
    分かれている。列の位置ではなくリンク先（club_shinagawa / club_arakawa）で
    振り分ける。列がずれている行があっても取り違えないため。
    """
    out: dict[str, list[tuple[str, str]]] = {"shinagawa": [], "arakawa": []}
    category = ""
    tabs = {"undo": "運動系", "bunka": "文化系", "gijyutu": "技術系"}

    for m in re.finditer(
        r'<div class="tab-pane[^"]*" id="(\w+)">(.*?)(?=<div class="tab-pane|</div>\s*</div>\s*</div>)',
        html, re.S,
    ):
        category = tabs.get(m.group(1), "")
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", m.group(2), re.S):
            link = re.search(r'href="([^"]*club_(shinagawa|arakawa)[^"]*)"', cell)
            name = text_of(cell)
            if not name or not link:
                continue
            key = link.group(2)
            if name not in [n for n, _ in out[key]]:
                out[key].append((name, category))
    return out


def main() -> None:
    crawler = Crawler(3.0)

    print("アクセスページを取得します...")
    status, body = crawler.get(ACCESS_URL)
    access = parse_access(text_of(decode_html(body)))
    for k, v in access.items():
        print(f"  {k}: " + " / ".join(f"{s}駅 徒歩{m}分" for s, m in v))

    print("部活動ページを取得します...")
    status, body = crawler.get(CLUB_URL)
    clubs = parse_clubs_by_campus(strip_noise(decode_html(body)))
    for k, v in clubs.items():
        print(f"  {k}: {len(v)}件")

    schools, club_rows = [], []
    for c in CAMPUSES:
        lat, lon = geocode(crawler, c["full_address"])
        stations = access.get(c["key"], [])
        if not stations:
            sys.exit(f"{c['name']}: アクセス（駅・徒歩分）が取れませんでした")

        schools.append({
            "school_number": c["school_number"],
            "name": c["name"],
            "official_name": c["official"],
            "ward": c["ward"],
            "address": c["address"],
            # ⚠️ 全日制ではない。既定の検索（全日制）に混ざらないための区分
            "course_types": "高専",
            "departments": DEPARTMENTS,
            "department_note": DEPARTMENT_NOTE,
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            # 通学時間の計算に使う。「駅:徒歩分」を近い順に並べる
            "access": "|".join(f"{s}:{m}" for s, m in stations),
            "selection_type": "kosen",
            "selection_note": "高専は入試の方式が都立高校と異なるため、点数では判定していません",
            "source_master": SOURCE,
            "source_coord": SOURCE_COORD,
        })
        for name, category in clubs.get(c["key"], []):
            club_rows.append({
                "school_number": c["school_number"],
                "school_name": c["name"],
                "raw_name": name,
                "category": category,
                "source_url": CLUB_URL,
                "engine": "kosen_table",
            })

    OUT_SCHOOLS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_SCHOOLS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(schools[0].keys()))
        w.writeheader()
        w.writerows(schools)
    with OUT_CLUBS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(club_rows[0].keys()))
        w.writeheader()
        w.writerows(club_rows)

    print(f"\n{OUT_SCHOOLS.relative_to(ROOT)} -> {len(schools)}校")
    print(f"{OUT_CLUBS.relative_to(ROOT)} -> {len(club_rows)}件")
    for s in schools:
        print(f"  {s['name']}  {s['ward']}  ({s['lat']},{s['lon']})  {s['access']}")


if __name__ == "__main__":
    main()
