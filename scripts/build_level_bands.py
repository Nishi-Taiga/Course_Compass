#!/usr/bin/env python3
"""レベル帯換算テーブルのドラフト生成。

方針（機能仕様書§5.2 / 偏差値は保持しない）:
- band 5/4/3 は都教委の進学指導指定区分で機械的に確定
  （5=重点校, 4=特別推進校, 3=推進校）
- それ以外の学校の band は空欄 = 塾講師（西）の専門判断で記入する
- 倍率は「難易度でなく人気」のため band 判定には使わず、参考列として併記
出力:
- data/seed/level_bands_draft.csv  … 1行=1校の記入シート
- data/seed/level_anchors_draft.csv … 自己申告値→帯の境界表（西記入用の骨格）
"""
import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
S = BASE / "data" / "seed"

DESIG_BAND = {"進学指導重点校": 5, "進学指導特別推進校": 4, "進学指導推進校": 3}


def main():
    master = list(csv.DictReader(open(S / "schools_master.csv")))

    # 参考情報: 普通科の応募倍率5年平均と直近値
    ratios = defaultdict(dict)   # school -> {year: ratio}（普通科優先）
    ratios_any = defaultdict(dict)
    for y in ("r4", "r5", "r6", "r7", "r8"):
        for r in csv.DictReader(open(S / f"ratios_{y}.csv")):
            if r["department"].startswith("普通科"):
                ratios[r["school"]][y] = float(r["ratio"])
            ratios_any[r["school"]].setdefault(y, float(r["ratio"]))

    rows = []
    for m in master:
        if "全日制" not in m["course_types"]:
            continue  # MVPは全日制のみ（仕様§4.4検索条件と整合）
        name = m["name"]
        band = DESIG_BAND.get(m["designation"], "")
        rs = ratios.get(name) or ratios_any.get(name) or {}
        avg = round(sum(rs.values()) / len(rs), 2) if rs else ""
        note = ""
        if not rs:
            note = "応募状況に不在=高校募集停止（中高一貫）の可能性。要確認"
        rows.append({
            "school": name,
            "ward": m["ward"],
            "departments": m["departments"],
            "designation": m["designation"],
            "band_draft": band,
            "band_final": "",          # ← 西が記入（3指定校以外＋指定校の妥当性確認）
            "note": note,              # ← 判断メモ（任意）
            "ref_ratio_avg_5yr": avg,  # 参考: 人気指標。band判定には使わない
            "ref_ratio_r8": rs.get("r8", ""),
        })

    rows.sort(key=lambda r: (-(r["band_draft"] or 0),
                             r["ref_ratio_avg_5yr"] if r["ref_ratio_avg_5yr"] != "" else -1),
              reverse=False)
    out = S / "level_bands_draft.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    filled = sum(1 for r in rows if r["band_draft"] != "")
    print(f"{len(rows)} 全日制校 -> {out.name}（band確定 {filled} / 記入待ち {len(rows)-filled}）")

    anchors = [
        {"band": 5, "label": "最難関（進学指導重点校クラス）",
         "mogi_hensachi_min": "", "naishin_min": "", "note": "西が境界を記入"},
        {"band": 4, "label": "難関（特別推進校クラス）",
         "mogi_hensachi_min": "", "naishin_min": "", "note": ""},
        {"band": 3, "label": "上位（推進校クラス）",
         "mogi_hensachi_min": "", "naishin_min": "", "note": ""},
        {"band": 2, "label": "中堅",
         "mogi_hensachi_min": "", "naishin_min": "", "note": ""},
        {"band": 1, "label": "基礎から伸ばす",
         "mogi_hensachi_min": "", "naishin_min": "", "note": "下限なし"},
    ]
    with open(S / "level_anchors_draft.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(anchors[0].keys()))
        w.writeheader()
        w.writerows(anchors)
    print("anchors -> level_anchors_draft.csv（境界値は西記入）")


if __name__ == "__main__":
    main()
