#!/usr/bin/env python3
"""プロトタイプの学校データに、定時制のみの15校を足す。

なぜ足すか（2026-08-19 欠陥チェックで発覚）
  「夜間の定時制も見たい」と言われても、D.schools に定時制のみの学校が
  1校も無く、希望が黙って無視されていた。APIは #15 で15校を持っている。
  プロトタイプだけが古い母集団のままだった。

⚠️ 目安点（t）は入れない。定時制は学力検査の教科数が学校ごとに違い、
   全日制の目安点では判定できない（西の判断は保留中・scoring.js と同じ扱い）。
   st='teiji' で区別し、画面では圏の判定をしない。
⚠️ 既定の検索には出さない。「定時制」と希望されたときだけ足す（API と同じ）。

出典: schools_master.csv（都教委 都立高校一覧）
      school_coords.csv / school_nearest_station.csv
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
PROTO = BASE / "prototype" / "index.html"

NOTE = ("定時制は学力検査の教科数や時間帯が学校ごとに違うため、"
        "ここでは点数の判定はしていません。募集案内でご確認ください")


def read(name: str, key: str = "name") -> dict:
    return {r[key]: r for r in csv.DictReader(open(SEED / name, encoding="utf-8"))}


def main() -> None:
    master = read("schools_master.csv")
    coords = read("school_coords.csv")
    near = read("school_nearest_station.csv")

    html = PROTO.read_text(encoding="utf-8")
    start = html.index("const D = ")
    end = html.index("\n", start)
    data = json.loads(html[start + len("const D = "):end].rstrip(";"))
    xy, wards = data["xy"], set(data["wards"])

    added = []
    for name, m in master.items():
        if m["course_types"] != "定時制":
            continue
        if any(s["n"] == name for s in data["schools"]):
            continue
        if name not in coords or name not in near:
            sys.exit(f"{name} の座標または最寄駅がありません。")
        st = near[name]["station"]
        if st not in xy or m["ward"] not in wards:
            sys.exit(f"{name}: 駅 {st} か区市 {m['ward']} がプロトタイプ側にありません。")
        data["schools"].append({
            "n": name, "w": m["ward"], "d": m["departments"] or "普",
            "g": "", "b": 0, "r": [], "x": 0,
            "t": None,                    # 目安点は持たない（冒頭コメント参照）
            "st": "teiji", "sn": NOTE, "ly": "定時制",
            "la": float(coords[name]["lat"]), "lo": float(coords[name]["lon"]),
            "ac": {"st": st, "la": xy[st][0], "lo": xy[st][1],
                   "md": "walk", "mi": int(float(near[name]["walk_min"])),
                   "dt": f"{st}駅から徒歩{int(float(near[name]['walk_min']))}分（直線距離からの概算）"},
        })
        added.append(name)

    new = "const D = " + json.dumps(data, ensure_ascii=False) + ";"
    PROTO.write_text(html[:start] + new + html[end:], encoding="utf-8")
    print(f"追加 {len(added)}校: {'・'.join(added) or 'なし'} / D.schools: {len(data['schools'])}校")


if __name__ == "__main__":
    main()
