#!/usr/bin/env python3
"""吹奏楽コンクールの審査結果PDFから、都立高校の賞を取り出す。

PDFは「プログラムNO / 学校名 / 賞」の並びで、行末に「最優秀」「代表」が
付くことがある。組（A/B/C/東日本）と日付は本文の見出し行に書かれているので、
ファイル名ではなく**本文から読む**（一覧ページ側の見出し対応は取り違えたため）。

⚠️ 個人情報: このPDFに生徒の氏名は含まれない（学校名と賞のみ）。
   それでも他ソースと同じ検査を通し、氏名らしき記述が現れたら異常終了する。

賞の意味（保護者に誤解させないため）:
  金賞 …… その組の最上位。ただし**金賞は複数校**出る（相対評価ではない）
  最優秀 … 金賞のうち上位。都大会や上位大会の代表になる
  代表 …… 上位大会へ進む

出力: data/seed/school_suisou_results.csv
      （school_club_achievements.csv と同じ列にそろえる）
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
SRC = BASE / "data" / "fetched" / "suisou"
SEED = BASE / "data" / "seed"
OUT = SEED / "school_suisou_results.csv"

# 「1 都立多摩科学技術高等学校 銅」「24 東海大学菅生高等学校 金 最優秀」
ROW = re.compile(r"^\s*(\d{1,3})\s+(\S.*?)\s+(金|銀|銅)\s*(最優秀|優秀|代表)?\s*$")
# 本文中の見出し「１３日　B組　どりーむホール」「A組」など
SECTION = re.compile(r"([ＡＢＣA-C]|東日本)\s*組")
# 回次 → 年度。第63回=令和5年度（2023）を起点に1回=1年
KAI_BASE, YEAR_BASE = 63, 5

NAME_LIKE = re.compile(r"[一-龥]{1,4}\s+[一-龥]{1,4}(?:\s|$)")


def load_schools() -> list[tuple[str, str]]:
    path = SEED / "school_sites.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return sorted(((r["school_number"], r["name"]) for r in rows),
                  key=lambda x: len(x[1]), reverse=True)


def match_school(cell: str, schools) -> tuple[str, str] | None:
    """「都立多摩科学技術高等学校」→ 学校マスタに突き合わせる。都立以外は None。"""
    if "都立" not in cell:
        return None
    body = cell.split("都立", 1)[1].replace("高等学校", "").strip()
    for number, name in schools:
        if body.startswith(name):
            return number, name
    return None


def main() -> None:
    index = SRC / "index.csv"
    if not index.is_file():
        sys.exit("fetch_suisou_results.py を先に実行してください。")
    schools = load_schools()
    meta = {r["file"]: r for r in csv.DictReader(open(index, encoding="utf-8"))}

    out = []
    for path in sorted(SRC.glob("*.pdf")):
        info = meta.get(path.name, {})
        kai = info.get("kai") or ""
        year = (f"令和{YEAR_BASE + int(kai) - KAI_BASE}年度"
                if kai.isdigit() else "")
        with pdfplumber.open(path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)

        section = ""
        for line in text.split("\n"):
            # 見出し行なら組を更新（「１３日　B組　…」「Ａ組　審査結果」）
            if "審査結果" in line or re.search(r"\d+\s*日", line):
                s = SECTION.search(line)
                if s:
                    section = s.group(1).translate(
                        str.maketrans("ＡＢＣ", "ABC")) + "組"
                continue
            m = ROW.match(line)
            if not m:
                continue
            hit = match_school(m.group(2), schools)
            if not hit:
                continue
            rank = m.group(3) + "賞"
            if m.group(4):
                rank += f"・{m.group(4)}"
            out.append({
                "school_number": hit[0], "school": hit[1], "year": year,
                "meet": f"東京都高等学校吹奏楽コンクール（第{kai}回）" if kai else "東京都高等学校吹奏楽コンクール",
                "sport": "吹奏楽", "event": section, "division": "",
                "rank": rank, "source": info.get("url", ""),
            })

    # 同じ学校が同じ回・同じ組で二重に出ることはない前提。念のため落とす
    seen, rows = set(), []
    for r in out:
        key = (r["school_number"], r["year"], r["event"], r["rank"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)

    # 氏名が紛れていないかの検査（他ソースと同じ作法）
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
    for k, v in Counter(r["rank"] for r in rows).most_common():
        print(f"  {k}: {v}件")
    print(f"  年度: {sorted({r['year'] for r in rows if r['year']})}")


if __name__ == "__main__":
    main()
