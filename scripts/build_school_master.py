#!/usr/bin/env python3
"""都教委CSV（公立学校統計調査報告書）から学校マスタを整形する。

入力: data/fetched/hs_address_csv.csv（住所録・cp932）
      data/fetched/hs_zennichisei_csv.csv（全日制 学科別・cp932）
      data/fetched/hs_teijisei_csv.csv（定時制 学科別・cp932）
      data/seed/designations.csv（進学指導指定区分）
出力: data/seed/schools_master.csv（1行=1校）
"""
import codecs
import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
F = BASE / "data" / "fetched"
S = BASE / "data" / "seed"


def read_cp932(path):
    with codecs.open(path, encoding="cp932") as f:
        return list(csv.DictReader(f))


def main():
    addr = read_cp932(F / "hs_address_csv.csv")
    zen = read_cp932(F / "hs_zennichisei_csv.csv")
    tei = read_cp932(F / "hs_teijisei_csv.csv")
    desig = {r["school_name"]: r["designation"]
             for r in csv.DictReader(open(S / "designations.csv"))}

    # 学科と生徒数を学校単位に集約
    depts = defaultdict(list)      # 学校番号 -> [大学科]
    students = defaultdict(int)    # 学校番号 -> 全日制生徒数計
    has_zen, has_tei = set(), set()
    for r in zen:
        no = r["学校番号"]
        d = (r.get("全日制/学科/大学科") or "").strip()
        if d and d not in ("…", "-") and d not in depts[no]:
            depts[no].append(d)
        v = (r.get("全日制/生徒数/計") or "").replace(",", "").strip()
        if v.isdigit():
            students[no] += int(v)
        if d and d not in ("…", "-"):
            has_zen.add(no)
    for r in tei:
        no = r["学校番号"]
        d = (r.get("定時制等/大学科") or r.get("定時制等/小学科") or "").strip()
        if d and d not in ("…", "-"):
            has_tei.add(no)

    rows = []
    for r in addr:
        no = r["学校番号"]
        name = r["学校名"].strip()
        course = []
        if no in has_zen:
            course.append("全日制")
        if no in has_tei:
            course.append("定時制")
        rows.append({
            "school_number": no,
            "name": name,
            "name_kana": r.get("学校名(フリガナ)", "").strip(),
            "ward": r.get("所在地区市町村", "").strip(),
            "postal_code": r.get("郵便番号", "").strip(),
            "address": r.get("住所", "").strip(),
            "phone": r.get("電話番号", "").strip(),
            "course_types": "・".join(course) or "要確認",
            "departments": "・".join(depts.get(no, [])),
            "students_fulltime": students.get(no, ""),
            "designation": desig.get(name, ""),
        })

    out = S / "schools_master.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} schools -> {out.name}")
    print("  全日制:", len(has_zen), "定時制:", len(has_tei),
          "指定区分付与:", sum(1 for r in rows if r["designation"]))
    # 検証: 指定29校がマスタに全部いるか
    missing = [n for n in desig if n not in {r["name"] for r in rows}]
    print("  指定区分でマスタ不在:", missing or "なし")


if __name__ == "__main__":
    main()
