#!/usr/bin/env python3
"""プロトタイプの学校データに制服情報（D.schools[].uf）を足す。

data/seed/school_uniforms.csv から、種類・スラックス/スカート選択可・
学校の記述の一節・出典URLを比べるシート用に入れる。

方針（安田の指摘 2026-08-17 を受けた設計）:
  - 種類はページの語から機械判定した範囲だけ。形が書かれていない学校は
    「制服あり（形は公式サイト参照）」、記述自体がない学校は載せない
  - 写真は各校の著作物なので使わない。出典リンクで公式ページに誘導する
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
PROTO = BASE / "prototype" / "index.html"


def main() -> None:
    rows = {r["name"]: r for r in
            csv.DictReader(open(SEED / "school_uniforms.csv", encoding="utf-8"))}

    html = PROTO.read_text(encoding="utf-8")
    start = html.index("const D = ")
    end = html.index("\n", start)
    data = json.loads(html[start + len("const D = "):end].rstrip(";"))

    added = 0
    for s in data["schools"]:
        r = rows.get(s["n"])
        if r and r["uniform_type"]:
            s["uf"] = {"t": r["uniform_type"],
                       "c": 1 if r["slacks_skirt_choice"] else 0,
                       "q": r["quote"], "u": r["source"]}
            added += 1
        else:
            s.pop("uf", None)

    out = "const D = " + json.dumps(data, ensure_ascii=False) + ";"
    PROTO.write_text(html[:start] + out + html[end:], encoding="utf-8")
    print(f"制服情報を入れた学校: {added}校")


if __name__ == "__main__":
    main()
