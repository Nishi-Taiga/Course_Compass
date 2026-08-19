#!/usr/bin/env python3
"""高校生国際美術展のPDFから、都立高校の入賞・佳作を取り出す。

⚠️ 個人情報（本PJの方針・2026-08-15 西の判断）
   このPDFは「氏名 作品名 都道府県 学校名 学年」の並びで、**氏名が主**。
   伏せるのではなく、**学校名だけを正規表現で切り出して他は読まない**。
   書き出す前に氏名らしき記述が混ざっていないか検査し、見つかれば異常終了する
   （高野連の試合結果と同じ作法）。

賞の区分はページ見出しから取る。
  「…入賞・学校賞」のページ → 入賞
  「…佳作」のページ         → 佳作
入賞のほうが上位。個別の賞名（都知事賞・秀作賞など）はページ内で
学校行と対応づけられないため、区分までに留める（推測で当てない）。

出力: data/seed/school_ifac_results.csv
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber が必要です: pip install pdfplumber")

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "fetched" / "ifac"
SEED = BASE / "data" / "seed"
OUT = SEED / "school_ifac_results.csv"

# 学校名だけを切り出す。氏名・作品名はこの正規表現に入らない
SCHOOL = re.compile(r"東京都立([^\s　、）]{1,12}?)高等学校")
# 第27回=2026年 を起点に、1回=1年で年度を割り出す
KAI_BASE, YEAR_BASE = 27, 8      # 第27回 → 令和8年度

NAME_LIKE = re.compile(r"[一-龥]{1,4}[\s　]+[一-龥]{1,4}")


def load_schools() -> list[tuple[str, str]]:
    rows = list(csv.DictReader(open(SEED / "school_sites.csv", encoding="utf-8")))
    return sorted(((r["school_number"], r["name"]) for r in rows),
                  key=lambda x: len(x[1]), reverse=True)


def match_school(body: str, schools) -> tuple[str, str] | None:
    for number, name in schools:
        if body.startswith(name):
            return number, name
    return None


def main() -> None:
    index = SRC / "index.csv"
    if not index.is_file():
        sys.exit("fetch_ifac_results.py を先に実行してください。")
    schools = load_schools()

    out = []
    for info in csv.DictReader(open(index, encoding="utf-8")):
        path = SRC / info["file"]
        if not path.is_file():
            continue
        kai = int(info["kai"])
        year = f"令和{YEAR_BASE + kai - KAI_BASE}年度"
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                head = text.split("\n")[0] if text else ""
                kind = "入賞" if "入賞" in head else ("佳作" if "佳作" in head else "")
                if not kind:
                    continue
                # ★ 学校名だけを拾う。行全体（氏名を含む）は保持しない
                for body in SCHOOL.findall(text):
                    hit = match_school(body, schools)
                    if not hit:
                        continue
                    out.append({
                        "school_number": hit[0], "school": hit[1], "year": year,
                        "meet": f"高校生国際美術展（第{kai}回）",
                        "sport": info["part"], "event": "", "division": "",
                        "rank": kind, "source": info["url"],
                    })

    seen, rows = set(), []
    for r in out:
        key = (r["school_number"], r["year"], r["sport"], r["rank"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)

    # 氏名が紛れていないかの検査。学校名の列に空白区切りの漢字が並ぶことはない
    leaked = [r for r in rows if NAME_LIKE.search(r["school"])]
    if leaked:
        sys.exit(f"個人名らしき記述が混入しています: {leaked[:3]}")

    fields = ["school_number", "school", "year", "meet", "sport", "event",
              "division", "rank", "source"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["school_number"], r["year"])))

    from collections import Counter
    print(f"{len(rows)}件 / {len({r['school_number'] for r in rows})}校 → {OUT}")
    for k, v in Counter((r["sport"], r["rank"]) for r in rows).most_common():
        print(f"  {k[0]} {k[1]}: {v}件")
    print(f"  年度: {sorted({r['year'] for r in rows})}")
    print("※ 生徒の氏名・作品名は読み取っていません")


if __name__ == "__main__":
    main()
