#!/usr/bin/env python3
"""都高体連の成績一覧PDFから、都立高校の部の実績だけを取り出す。

⚠️ 個人情報の扱い（2026-08-15 西の判断）
   PDFには出場生徒の氏名・学年・記録が載っている。**これらは一切保存しない。**
   保護者が知りたいのは「この学校のこの部が関東大会に行っている」であって
   誰が走ったかではない。列ごと捨てるので、後段の処理に氏名が漏れることはない。
   保持するのは 学校・年度・大会・競技・種目・区分・順位 だけ。

PDFは2種類の書式がある。
  ① 都総体の団体成績    … 種目 | 男女 | 1位 | 2位 | 3位 | 4位（学校名が入る）
  ② 関東・IH の個人成績 … 種目名|選手名|学年|学校名|記録|成績 が男子6列＋女子6列
どちらも pdfplumber が表として読めるので、座標を自前で扱う必要はない。

出力: data/seed/school_club_achievements.csv
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
PDF_DIR = BASE / "data" / "fetched" / "kotairen"
SEED = BASE / "data" / "seed"
OUT = SEED / "school_club_achievements.csv"

# 順位・成績の表現。「決勝12位」「ベスト8」「優勝」「決勝出場」など
RANK_RE = re.compile(r"(優勝|準優勝|ベスト\s*\d+|(?:決勝|準決勝|準々決勝|予選)?\s*\d+\s*位"
                     r"|(?:決勝|準決勝)?出場|入賞|\d+\s*回戦)")


def load_schools() -> list[tuple[str, str]]:
    """(学校番号, 学校名) を長い名前順で返す。前方一致の取り違えを防ぐため。"""
    path = SEED / "school_sites.csv"
    if not path.is_file():
        sys.exit(f"{path} がありません。build_school_sites.py を先に実行してください。")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return sorted(((r["school_number"], r["name"]) for r in rows),
                  key=lambda x: len(x[1]), reverse=True)


def match_school(cell: str, schools) -> tuple[str, str] | None:
    """セルの学校名を都立高校マスタに突き合わせる。都立以外は None。

    PDFは「都立松が谷」「都立南多摩中等教育学校」のように都立を冠する。
    冠していない＝私立・国立なので対象外（本サービスは都立のみ扱う）。
    """
    if not cell or "都立" not in cell:
        return None
    # 「都立小平西／淑徳」「都立井草・国士館」のような合同チーム表記は先頭校を採る
    body = re.split(r"[／/・、]", cell.split("都立", 1)[1])[0].strip()
    if not body:
        return None
    for number, name in schools:
        if body.startswith(name):
            return number, name
    return None


def parse_team_table(table, ctx, schools, out):
    """①都総体の団体成績。1位〜4位の列に学校名が並ぶ。"""
    sport = ""
    for row in table:
        cells = [(c or "").replace("\n", "").strip() for c in row]
        if len(cells) < 6 or "１位" in cells or "団 体 成 績" in "".join(cells):
            continue
        # 種目名は同じ競技の男女で片方が空欄になる。直前の値を引き継ぐ
        if cells[1]:
            sport = cells[1]
        div = cells[2] if cells[2] in ("男", "女") else ""
        for i, rank in enumerate(("1位", "2位", "3位", "4位")):
            if 3 + i >= len(cells):
                break
            hit = match_school(cells[3 + i], schools)
            if hit:
                out.append({**ctx, "school_number": hit[0], "school": hit[1],
                            "sport": sport, "event": "団体", "division": div,
                            "rank": rank})


# 見出し語。年度によって列数も呼び名も変わる（令和5は10列「名前/所属」、
# 令和6以降は12列「選手名/学年/学校名」、定通制はまた別）。位置を決め打ちせず、
# 見出し行から列番号を割り出す。
H_SCHOOL = ("学校名", "所属")
H_RESULT = ("成績", "順位")
H_EVENT = ("種目名", "競技種目", "種目")
H_DROP = ("選手名", "名前", "氏名", "学年", "記録")     # ← 保存しない列


def column_map(cells: list[str]) -> dict | None:
    """見出し行から、男子側・女子側それぞれの (種目, 学校, 成績) の列番号を得る。"""
    idx = {"school": [], "result": [], "event": []}
    for i, c in enumerate(cells):
        c = c.replace(" ", "")
        if c in H_SCHOOL:
            idx["school"].append(i)
        elif c in H_RESULT:
            idx["result"].append(i)
        elif c in H_EVENT:
            idx["event"].append(i)
    if not idx["school"] or not idx["result"]:
        return None
    # 男女で同じ見出しが2組並ぶ。学校列の数だけブロックがあるとみなす
    blocks = []
    for n, sc in enumerate(idx["school"]):
        rs = [r for r in idx["result"] if r > sc]
        if not rs:
            continue
        ev = [e for e in idx["event"] if e < sc]
        blocks.append({"school": sc, "result": rs[0],
                       "event": ev[-1] if ev else None,
                       "division": "男" if n == 0 else "女"})
    return {"blocks": blocks} if blocks else None


def parse_individual_table(table, ctx, schools, out):
    """②関東・IH・定通制の個人成績。**選手名・学年・記録は列ごと捨てる。**"""
    cols = None
    sport = ""            # 「1.2.陸上競技」のような競技見出し行
    event: dict[str, str] = {}
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        joined = "".join(cells).replace(" ", "")
        if any(h in joined for h in H_DROP) and any(h in joined for h in H_SCHOOL):
            cols = column_map(cells) or cols
            continue
        if cols is None:
            continue
        # 競技見出し（1列目だけに入り、他が空）
        if cells[0] and not any(cells[1:]):
            sport = re.sub(r"^[\d.\s]+", "", cells[0]).strip()
            continue
        for b in cols["blocks"]:
            if b["school"] >= len(cells) or b["result"] >= len(cells):
                continue
            div = b["division"]
            if b["event"] is not None and b["event"] < len(cells) and cells[b["event"]]:
                event[div] = cells[b["event"]]     # 同一種目の2人目以降は空欄
            hit = match_school(cells[b["school"]], schools)
            if not hit:
                continue
            m = RANK_RE.search(cells[b["result"]])
            if not m:
                continue
            out.append({**ctx, "school_number": hit[0], "school": hit[1],
                        "sport": sport, "event": event.get(div, ""), "division": div,
                        "rank": re.sub(r"\s+", "", m.group(1))})


def meet_of(label: str) -> str:
    if "全国高等学校総合体育大会" in label:
        return "全国大会（インターハイ）"
    if "関東高等学校総合体育大会" in label:
        return "関東大会"
    if "定時制通信制" in label:
        return "全国大会（定時制通信制）"
    if "東京都高等学校総合体育大会" in label:
        return "東京都大会"
    return label


def main() -> None:
    schools = load_schools()
    index = PDF_DIR / "index.csv"
    if not index.is_file():
        sys.exit("data/fetched/kotairen/index.csv がありません。"
                 "fetch_kotairen_results.py を先に実行してください。")

    out: list[dict] = []
    for row in csv.DictReader(open(index, encoding="utf-8")):
        path = PDF_DIR / row["file"]
        if not path.is_file():
            continue
        year = re.search(r"令和\s*(元|\d+)\s*年度", row["label"])
        ctx = {
            "year": f"令和{year.group(1)}年度" if year else "",
            "meet": meet_of(row["label"]),
            "source": row["url"],
        }
        team = "東京都高等学校総合体育大会" in row["label"]
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if team:
                        parse_team_table(table, ctx, schools, out)
                    else:
                        parse_individual_table(table, ctx, schools, out)
        print(f"  {row['file']}: 累計 {len(out)}件")

    # 同じ実績が複数行に出ることがある（団体戦の重複掲載など）
    seen, rows = set(), []
    for r in out:
        key = tuple(r[k] for k in ("school_number", "year", "meet", "sport", "event",
                                   "division", "rank"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)

    fields = ["school_number", "school", "year", "meet", "sport", "event",
              "division", "rank", "source"]
    assert not ({"name", "選手名", "grade", "record"} & set(fields)), "個人情報の列が混入"
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["school_number"], r["year"])))

    print(f"\n実績 {len(rows)}件 / {len({r['school_number'] for r in rows})}校 → {OUT}")
    print("※ 選手名・学年・記録は保存していません")


if __name__ == "__main__":
    main()
