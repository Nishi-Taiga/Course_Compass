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

MEET_RANK = {"全国大会（インターハイ）": 3, "全国大会（定時制通信制）": 3, "全国大会": 3,
             "関東大会": 2, "東京都大会": 1, "東京都大会（予選）": 1}
# 吹奏楽コンクールは都のコンクール。大会の格としては都大会と同じ扱い
SUISOU_MEET = "東京都高等学校吹奏楽コンクール"
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
    # 吹奏楽の賞。金賞は複数校出るので「優勝」と同格にはしない
    if rank.startswith("金賞"):
        return 88 if "最優秀" in rank else 75
    if rank.startswith("銀賞"):
        return 55
    if rank.startswith("銅賞"):
        return 40
    # 美術展の区分。入賞が上、佳作がその下
    if rank == "入賞":
        return 70
    if rank == "佳作":
        return 45
    # 野球の勝ち上がり。回戦が進むほど上。一回戦出場は最も軽い
    m = re.match(r"([一二三四五六七八九])回戦(進出|出場)", rank)
    if m:
        n = "一二三四五六七八九".index(m.group(1)) + 1
        return 12 + n * 6
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


def load_site_rows() -> list[dict]:
    """学校サイト側の実績を、連盟の記録と同じ形にそろえて返す。

    連盟の一覧に載らない範囲（都大会の5位以下、高野連・高文連の管轄）を補う。
    自動採用可(OK)のものだけを使う。要確認は人の確認を経ていないので入れない。
    """
    path = SEED / "school_club_achievements_sites.csv"
    if not path.is_file():
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["flag"] != "OK" or not r["club"] or not r["meet"]:
            continue
        rank = re.search(r"優勝|準優勝|ベスト\s*[0-9０-９]+|第?\s*[0-9０-９]+\s*位"
                         r"|入賞|金賞|銀賞|銅賞|出場", r["text"])
        if not rank:
            continue
        out.append({"school": r["school"], "sport": r["club"], "event": "",
                    "division": "", "meet": r["meet"], "rank": rank.group(0),
                    "year": r["year"], "origin": "学校公式サイト"})
    return out


def load_suisou() -> list[dict]:
    """吹奏楽コンクールの結果。高体連の管轄外なので別ファイルから読む。

    金賞は複数校出るため「1位」ではない。順位に読み替えず賞のまま出す。
    """
    path = SEED / "school_suisou_results.csv"
    if not path.is_file():
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        # 組（A/B/C/東日本）は編成規模の区分で、保護者には意味が伝わらない。
        # 競技名は「吹奏楽」に統一し、組は賞のうしろに小さく添える
        kumi = (r.get("event") or "").strip()
        out.append({**r, "sport": "吹奏楽", "event": "",
                    "rank": f"{r['rank']}（{kumi}）" if kumi else r["rank"],
                    "meet": "東京都大会", "origin": "東京都吹奏楽連盟"})
    return out


def load_ifac() -> list[dict]:
    """高校生国際美術展の結果（美術・書道）。

    入賞と佳作の2区分。個別の賞名はPDF上で学校行と対応づけられないので
    区分までに留める（推測で当てない）。
    """
    path = SEED / "school_ifac_results.csv"
    if not path.is_file():
        return []
    return [{**r, "meet": "全国大会", "origin": "高校生国際美術展"}
            for r in csv.DictReader(open(path, encoding="utf-8"))]


def load_baseball() -> list[dict]:
    """硬式野球（高野連）の結果。

    ⚠️ 1,263件のうち639件が「一回戦出場」で、大半が初戦の記録。
    そのまま出すと、勝ち上がった学校と初戦だけの学校が同じ重みに見える。
    大会の格は都大会として扱い、重み付け（rank_score）で差を付ける。
    """
    path = SEED / "school_baseball_results.csv"
    if not path.is_file():
        return []
    return [{**r, "meet": "東京都大会", "origin": "東京都高等学校野球連盟"}
            for r in csv.DictReader(open(path, encoding="utf-8"))]


def main() -> None:
    rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8"))
            if (r["sport"] or r["event"])]          # 競技が分からない行は出さない
    for r in rows:
        r["origin"] = "都高体連"
    rows += load_suisou() + load_ifac() + load_baseball()

    best: dict[str, dict] = {}
    # 連盟を先に入れる。同じ学校・競技で学校サイト側と重なったら連盟を優先する
    # （連盟は第三者の公式記録、学校サイトは自己申告のため）
    for r in rows + load_site_rows():
        sport = label_sport(r)
        if not sport:
            continue
        key = (r["school"], sport, r["division"])
        score = (MEET_RANK.get(r["meet"], 0), rank_score(r["rank"]))
        cur = best.get(key)
        if cur is not None and cur["origin"] == "都高体連" and r["origin"] != "都高体連":
            continue
        if cur is None or score > cur["_score"]:
            best[key] = {"_score": score, "school": r["school"], "sport": sport,
                         "division": r["division"], "meet": r["meet"],
                         "rank": r["rank"], "year": r["year"], "origin": r["origin"]}

    def display_rank(meet: str, rank: str) -> str:
        """全国・関東は、上位でない順位を「出場」に丸める。

        インターハイ95位は弱さの証拠ではなく、全国に出たという事実のほうが
        保護者に伝わる。順位で誤解させない（元の順位はCSVに残る）。
        """
        if "賞" in rank or rank in ("入賞", "佳作"):
            return rank            # 金銀銅・入賞・佳作は順位ではないので丸めない
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
                        "rk": display_rank(i["meet"], i["rank"]), "yr": i["year"],
                        "sr": i["origin"]}
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
