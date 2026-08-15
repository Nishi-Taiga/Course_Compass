#!/usr/bin/env python3
"""プロトタイプの学校データに、部の実績（都高体連の公式記録）を足す。

data/seed/school_club_achievements.csv を読み、学校ごとに
「競技・区分」単位でいちばん上の実績だけを残して D.schools[].ach に入れる。

方針（2026-08-15 西の判断）
  - 出場生徒の氏名・学年・記録は元データの時点で保持していない。部の実績として出す
  - 競技名も種目名も取れなかった行は表示しない。「関東大会 3位」だけでは
    何の3位か分からず、読み手に意味が伝わらないため（記録としてはCSVに残る）
  - 全国大会は順位より「出場」が伝わることを優先する。インターハイの44位は
    弱さではなく全国に出たという事実なので、順位を強調しない
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
PROTO = BASE / "prototype" / "index.html"
SRC = SEED / "school_club_achievements.csv"

MEET_RANK = {"全国大会（インターハイ）": 3, "全国大会（定時制通信制）": 3,
             "関東大会": 2, "東京都大会": 1}
MAX_PER_SCHOOL = 4


def rank_score(rank: str) -> int:
    """順位の重み。上位ほど大きい。"""
    if "優勝" == rank:
        return 100
    if "準優勝" == rank:
        return 95
    m = re.match(r"ベスト\s*(\d+)", rank)
    if m:
        return max(50, 90 - int(m.group(1)))
    m = re.search(r"(\d+)\s*位", rank)
    if m:
        return max(20, 92 - int(m.group(1)) * 2)
    if "出場" in rank:
        return 15
    m = re.match(r"(\d+)\s*回戦", rank)
    if m:
        return 10 + int(m.group(1))
    return 5


def label_sport(row: dict) -> str:
    """表示用の競技名。競技と種目の両方があれば競技を優先しつつ種目を添える。"""
    sport = (row["sport"] or "").strip()
    event = (row["event"] or "").strip()
    if sport and event and event != "団体" and event not in sport:
        return f"{sport}{event}" if len(sport + event) <= 16 else sport
    return sport or event


def main() -> None:
    rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8"))
            if (r["sport"] or r["event"])]          # 競技が分からない行は出さない

    best: dict[str, dict] = {}
    for r in rows:
        sport = label_sport(r)
        if not sport:
            continue
        key = (r["school"], sport, r["division"])
        score = (MEET_RANK.get(r["meet"], 0), rank_score(r["rank"]))
        cur = best.get(key)
        if cur is None or score > cur["_score"]:
            best[key] = {"_score": score, "school": r["school"], "sport": sport,
                         "division": r["division"], "meet": r["meet"],
                         "rank": r["rank"], "year": r["year"]}

    def display_rank(meet: str, rank: str) -> str:
        """全国・関東は、上位でない順位を「出場」に丸める。

        インターハイ95位は弱さの証拠ではなく、全国に出たという事実のほうが
        保護者に伝わる。順位で誤解させない（元の順位はCSVに残る）。
        """
        if MEET_RANK.get(meet, 0) < 2:
            return rank
        m = re.fullmatch(r"(?:決勝|準決勝|準々決勝|予選)?\s*(\d+)\s*位", rank)
        if m and int(m.group(1)) > 8:
            return "出場"
        if re.fullmatch(r"\d+\s*回戦", rank):
            return "出場"
        return rank

    by_school: dict[str, list] = {}
    for v in best.values():
        by_school.setdefault(v["school"], []).append(v)

    out: dict[str, list] = {}
    for school, items in by_school.items():
        items.sort(key=lambda x: x["_score"], reverse=True)
        # 「なぎなた個人 優勝」の下に「なぎなた 出場」が並ぶと、同じ部の実績が
        # 二重に見える。競技名だけの行は、より具体的な行があるなら落とす
        specific = {(i["sport"], i["division"]) for i in items}
        items = [i for i in items
                 if not any(o != i["sport"] and o.startswith(i["sport"])
                            for o, d in specific if d == i["division"])]
        out[school] = [{"sp": i["sport"], "dv": i["division"], "mt": i["meet"],
                        "rk": display_rank(i["meet"], i["rank"]), "yr": i["year"]}
                       for i in items[:MAX_PER_SCHOOL]]

    html = PROTO.read_text(encoding="utf-8")
    start = html.index("const D = ")
    end = html.index("\n", start)
    data = json.loads(html[start + len("const D = "):end].rstrip(";"))

    added = 0
    for s in data["schools"]:
        ach = out.get(s["n"])
        if ach:
            s["ach"] = ach
            added += 1
        else:
            s.pop("ach", None)

    new = "const D = " + json.dumps(data, ensure_ascii=False) + ";"
    PROTO.write_text(html[:start] + new + html[end:], encoding="utf-8")
    print(f"実績を入れた学校: {added}校 / 表示対象 {len(rows)}件（元データ {sum(1 for _ in csv.DictReader(open(SRC, encoding='utf-8')))}件）")


if __name__ == "__main__":
    main()
