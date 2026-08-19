#!/usr/bin/env python3
"""プロトタイプの学校データに、都立産業技術高専の2キャンパスを足す。

なぜ別扱いか
  高専は都教委の「都立高校一覧」に載らない（高等学校ではなく高等専門学校）。
  プロトタイプの D.schools は都立高校の一覧から作ったので、そのままでは
  ものづくり志望の家庭にいちばん向いている選択肢が1つも出てこない。

⚠️ 目安点（t）は入れない。都立高校は5教科＋調査書、高専は3教科で、
   満点も配点も違う。同じ目安点を当てると過大評価になる（API側と同じ扱い）。
   代わりに st='kosen' と注記を入れ、画面では圏の判定をしない。

出典: data/seed/extra_schools.csv（東京都立産業技術高等専門学校 公式サイト）
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "seed" / "extra_schools.csv"
PROTO = BASE / "prototype" / "index.html"

NOTE = "高専は5年制で、入試も都立高校とは方式が違います（3教科＋調査書）。ここでは点数の判定はしていません"


def main() -> None:
    if not SRC.is_file():
        sys.exit(f"{SRC} がありません。")
    html = PROTO.read_text(encoding="utf-8")
    start = html.index("const D = ")
    end = html.index("\n", start)
    data = json.loads(html[start + len("const D = "):end].rstrip(";"))
    xy = data["xy"]
    wards = set(data["wards"])

    added, skipped = [], []
    for r in csv.DictReader(open(SRC, encoding="utf-8")):
        if r["course_types"] != "高専":
            continue
        if any(s["n"] == r["name"] for s in data["schools"]):
            skipped.append(r["name"])
            continue
        if r["ward"] not in wards:
            sys.exit(f"{r['name']} の所在区市 {r['ward']} が D.wards にありません。")

        # access は「駅名:徒歩分|駅名:徒歩分|…」の近い順。先頭を最寄りとして扱う
        first = r["access"].split("|")[0]
        st, mi = first.split(":")
        if st not in xy:
            sys.exit(f"最寄駅 {st} の座標が D.xy にありません（駅名の表記を確認）。")

        data["schools"].append({
            "n": r["name"], "w": r["ward"], "d": "工",
            "g": "", "b": 0, "r": [], "x": 0,
            "t": None,                     # 目安点は持たない（上のコメント参照）
            "st": "kosen", "sn": NOTE, "ly": "高専",
            "la": float(r["lat"]), "lo": float(r["lon"]),
            "ac": {"st": st, "la": xy[st][0], "lo": xy[st][1],
                   "md": "walk", "mi": int(mi),
                   "dt": r["department_note"]},
        })
        added.append(r["name"])

    new = "const D = " + json.dumps(data, ensure_ascii=False) + ";"
    PROTO.write_text(html[:start] + new + html[end:], encoding="utf-8")
    print(f"追加 {len(added)}校: {'・'.join(added) or 'なし'}"
          + (f" / 既にあり {len(skipped)}校" if skipped else ""))
    print(f"D.schools: {len(data['schools'])}校")


if __name__ == "__main__":
    main()
