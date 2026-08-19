#!/usr/bin/env python3
"""プロトタイプの学校データに、部活の一覧を埋め込む。

なぜ足すか（2026-08-19 欠陥チェックで発覚）
  部活データは5,033件そろっているのに、プロトタイプは「デモ版では部活データが
  準備中」と言って希望を無視していた。「吹奏楽をやりたい」と言っても
  吹奏楽の無い学校が平気で並ぶ。データがあるのに使わないのは準備中より悪い。

サイズを抑える工夫
  正規化名の異なりは約600語しかないので、語の一覧 D.cw を1つ置き、
  各校は語のindex配列 s.cb を持つ（素の名前を全校に持たせると+97KB、
  この方式なら+30KB程度）。表記ゆれ（バトミントン等）は正規化辞書で
  吸収済みなので、検索は正規化名でだけ当てればよい。

出典: school_clubs.csv（各校公式サイト）＋ 定時制・高専の同等CSV
      club_normalize.csv（西の監修済み正規化辞書）
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
PROTO = BASE / "prototype" / "index.html"

SOURCES = ["school_clubs.csv", "school_clubs_teiji.csv", "extra_school_clubs.csv"]


def main() -> None:
    norm = {r["raw_name"]: r["normalized"]
            for r in csv.DictReader(open(SEED / "club_normalize.csv", encoding="utf-8"))}

    by: dict[str, set] = defaultdict(set)
    total = 0
    for name in SOURCES:
        path = SEED / name
        if not path.is_file():
            continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            by[r["school_name"]].add(norm.get(r["raw_name"], r["raw_name"]))
            total += 1

    html = PROTO.read_text(encoding="utf-8")
    start = html.index("const D = ")
    end = html.index("\n", start)
    data = json.loads(html[start + len("const D = "):end].rstrip(";"))

    words = sorted({w for v in by.values() for w in v})
    idx = {w: i for i, w in enumerate(words)}
    hit = 0
    for s in data["schools"]:
        clubs = by.get(s["n"])
        if clubs:
            s["cb"] = sorted(idx[w] for w in clubs)
            s["b"] = len(clubs)           # 従来の部活数フィールドを実数に更新
            hit += 1
        else:
            s.pop("cb", None)

    data["cw"] = words
    new = "const D = " + json.dumps(data, ensure_ascii=False) + ";"
    PROTO.write_text(html[:start] + new + html[end:], encoding="utf-8")
    print(f"部活 {total}件 → 正規化{len(words)}語 / {hit}校に埋め込み"
          f"（部活CSVに無い学校 {sum(1 for s in data['schools'] if 'cb' not in s)}校＝中高一貫等）")


if __name__ == "__main__":
    main()
