#!/usr/bin/env python3
"""日本高校ダンス部選手権のPDFから、都立各校の実績を出す。

    python3 scripts/fetch_dance_results.py     # 先に取得
    python3 scripts/build_dance_results.py

出力: data/seed/school_dance_results.csv
      （school_club_achievements.csv と同じ列。attribute_achievements.py が合流させる）

## なぜ必要か

ダンス部は都立144校にあるのに実績が**1件も無かった**。高体連の70競技に
ダンスは無く、高文連にもダンス部門が無い。どちらの連盟にも属さない部活で、
連盟をたどる従来の経路では永久に埋まらない。

## 何を「実績」とするか

東京都大会が独立開催されるため、**出場そのもの**が都立60校超に付く。
「出場」を実績に数えるのは高野連と同じ扱い（そちらも「一回戦出場」を
実績として持っている）。上位まで進んだ学校には、より強い実績が上書きされる。

  全国決勝の得点表      → 優勝 / 準優勝 / ◯位
  全国決勝の出場校      → 全国決勝進出
  全国準決勝の出場校    → 全国準決勝進出
  準決勝出場校の順位欄  → 都大会 優勝 / 準優勝 / ◯位
  東京都大会の出場校    → 都大会出場

⚠️ 同じ大会・同じ年度に複数当てはまったら、**最も上のものだけ**を残す。
   「都大会出場」と「都大会優勝」が並ぶと、優勝が埋もれて読みにくい。

## PDFの形式が年で違う

⚠️ 2024年の準決勝PDFには順位欄が無く、出場校が並ぶだけ。2025年以降は
   「東京都 Ａブロック 優勝 東京都 東京都立狛江高等学校」と順位が入る。
   順位つきを先に拾い、拾えなかったものを出場として拾う。

⚠️ 2列組みのため、抽出した1行に2校ぶんが入る。行単位で finditer して
   両方を拾う。県名と校名が空白なしで繋がる行（「神奈川県白鵬女子高等学校」）
   があるので、校名は非貪欲に取る。

## 個人名について

⚠️ このPDFに生徒の氏名は載っていない（学校名と得点だけ）。高野連・演劇と
   違って避ける仕掛けは要らないが、形式が変わったときに気付けるよう検査は通す。
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
DANCE = ROOT / "data" / "fetched" / "dance"
INDEX_CSV = DANCE / "index.csv"
OUT = SEED / "school_dance_results.csv"

SOURCE = "日本高校ダンス部選手権（ダンススタジアム）大会結果"
MEET_TOKYO = "日本高校ダンス部選手権 東京都大会"
MEET_SEMI = "日本高校ダンス部選手権 全国準決勝大会"
MEET_FINAL = "日本高校ダンス部選手権 全国決勝大会"

# 都立校だけを拾う。県名と繋がる行があるので非貪欲。中等教育学校は
# 「高等学校」で終わらないため自然に外れる（高校からの募集が無い）
TORITSU_RE = re.compile(r"東京都立\S*?高等学校")
# 「… 優勝 東京都 東京都立狛江高等学校」。順位と校名が同じ行にある形
RANKED_RE = re.compile(r"(優勝|準優勝|\d+位)\s*東京都\s*(東京都立\S*?高等学校)")
# 得点表「7 4 東京都 東京都立狛江高等学校 37 37 …」。行頭が全国順位
SCORE_RE = re.compile(r"^\s*(\d+)\s+\d+\s+東京都\s*(東京都立\S*?高等学校)")

# 氏名らしき表記。このソースには本来無い。形式が変わったら気付くための番人
PERSON_RE = re.compile(r"さん|くん|[^校]君|選手(?![権団])|作[:：]")

# 強い実績ほど大きい。同じ大会・年度で最も大きいものだけを残す
def strength(rank: str) -> int:
    if rank == "優勝":
        return 1000
    if rank == "準優勝":
        return 999
    if m := re.fullmatch(r"(\d+)位", rank):
        return 998 - int(m.group(1))
    return {"全国決勝進出": 500, "全国準決勝進出": 400, "都大会出場": 100}.get(rank, 0)


def nendo(year: str) -> str:
    return f"令和{int(year) - 2018}年度"


def school_key(name: str) -> str:
    """「東京都立小山台高等学校」→「小山台」。学校マスタの表記に合わせる。"""
    return re.sub(r"高等学校$", "", re.sub(r"^東京都立", "", name))


def read_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def main() -> None:
    if not INDEX_CSV.is_file():
        sys.exit(f"{INDEX_CSV} がありません。先に fetch_dance_results.py を実行してください")

    master = {r["name"]: r for r in csv.DictReader(
        (SEED / "schools_master.csv").open(encoding="utf-8-sig"))}

    # (学校, 年度, 大会) -> (強さ, 順位)
    best: dict[tuple, tuple[int, str]] = {}
    unknown: set[str] = set()
    person_hits: list[str] = []
    seen_files = 0

    def put(name: str, year: str, meet: str, rank: str) -> None:
        key = school_key(name)
        if key not in master:
            unknown.add(name)
            return
        k = (key, nendo(year), meet)
        s = strength(rank)
        if k not in best or s > best[k][0]:
            best[k] = (s, rank)

    for row in csv.DictReader(INDEX_CSV.open(encoding="utf-8-sig")):
        path = DANCE / row["file"]
        if not path.is_file():
            continue
        seen_files += 1
        text = read_text(path)
        year, kind = row["year"], row["kind"]

        for line in text.splitlines():
            if PERSON_RE.search(line):
                person_hits.append(f"{row['file']}: {line[:60]}")

        if kind == "syutsujou_tokyo":
            # 順位つきの行があればそちらを優先。無ければ出場として拾う
            for line in text.splitlines():
                for m in RANKED_RE.finditer(line):
                    put(m.group(2), year, MEET_TOKYO, m.group(1))
            for name in TORITSU_RE.findall(text):
                put(name, year, MEET_TOKYO, "都大会出場")

        elif kind == "syutsujou_junkessyou":
            # 順位欄は「東京都大会での順位」。2024年のPDFにはこの欄が無い
            for line in text.splitlines():
                for m in RANKED_RE.finditer(line):
                    put(m.group(2), year, MEET_TOKYO, m.group(1))
            for name in TORITSU_RE.findall(text):
                put(name, year, MEET_SEMI, "全国準決勝進出")

        elif kind == "syutsujou_kessyou":
            for name in TORITSU_RE.findall(text):
                put(name, year, MEET_FINAL, "全国決勝進出")

        elif kind.startswith("tokuten"):
            for line in text.splitlines():
                if m := SCORE_RE.match(line):
                    n = int(m.group(1))
                    rank = "優勝" if n == 1 else "準優勝" if n == 2 else f"{n}位"
                    put(m.group(2), year, MEET_FINAL, rank)

    if not best:
        sys.exit("1件も取れませんでした。PDFの形式が変わった可能性があります")

    if person_hits:
        print("⚠️ 氏名らしき表記がPDFに現れました。読み取り範囲を確認してください。")
        for h in person_hits[:10]:
            print("   ", h)
        sys.exit(1)
    print("個人情報の検査: 問題なし（学校名・順位のみ）")

    rows = [{
        "school_number": master[name]["school_number"],
        "school": name,
        "year": year,
        "meet": meet,
        "sport": "ダンス",
        "event": "",
        "division": "",
        "rank": rank,
        "source": SOURCE,
    } for (name, year, meet), (_, rank) in sorted(best.items())]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"{OUT.relative_to(ROOT)} -> {len(rows)}件")
    print(f"  PDF {seen_files}本 / 都立 {len({r['school'] for r in rows})}校 "
          f"/ 年度 {sorted({r['year'] for r in rows})}")
    if unknown:
        print(f"  学校マスタに無い都立名 {len(unknown)}件: {sorted(unknown)[:5]}")


if __name__ == "__main__":
    main()
