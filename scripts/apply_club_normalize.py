#!/usr/bin/env python3
"""西の監修結果を正規化辞書に反映し、school_clubs.normalized を埋める。

監修結果（2026-08-19）
  Q1 男女別 → **分けたまま**。「男子バスケットボール」と「女子バスケットボール」は
     別の部として扱う。合同で活動していない以上、まとめると実態と合わない
  Q2 同好会・班 → **部と同列**に検索へ出す。小山台は部活動全体を「班」と呼ぶため、
     区別すると同校の部活が検索から漏れる
  Q3 表記ゆれ → 誤記と別名は統合する。硬式テニス／ソフトテニスは別物のまま

Q1・Q2 は辞書生成の時点で満たされていた。このスクリプトは Q3 の統合だけを
上乗せし、辞書を school_clubs に反映する。

⚠️ raw_name は書き換えない（元の表記に戻せなくなるため・仕様書§6.2）。
   normalized 列だけを埋める。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
DICT = SEED / "club_normalize.csv"
OUT = SEED / "club_normalize.csv"

# Q3: 誤記・別名の統合。左を右に寄せる。
# 「同じものを指しているのに別語として検索に出る」ものだけを入れる。
# 硬式テニス／ソフトテニス、男子／女子のように**別物**は入れない。
MERGE = {
    "バトミントン": "バドミントン",       # 誤記
    "ものつくり": "ものづくり",           # 表記ゆれ
    "コンピュータ": "コンピューター",     # 長音の有無
    "バレー": "バレーボール",             # 略称
    "バスケ": "バスケットボール",         # 略称
    "ESS": "英語",                        # 別名（同じ英語系の部）
}


def apply_merge(value: str) -> str:
    """男女の接頭辞は保ったまま、本体だけを寄せる。"""
    for prefix in ("男子", "女子", "男女"):
        if value.startswith(prefix):
            body = value[len(prefix):]
            return prefix + MERGE.get(body, body)
    return MERGE.get(value, value)


def main() -> None:
    if not DICT.is_file():
        sys.exit(f"{DICT} がありません。")
    rows = list(csv.DictReader(open(DICT, encoding="utf-8")))

    changed = []
    for r in rows:
        before = r["normalized"]
        after = apply_merge(before)
        if before != after:
            r["normalized"] = after
            r["decided_by"] = "西の監修(2026-08-19)"
            changed.append((r["raw_name"], before, after))

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"辞書 {len(rows)}行 / 統合した表記 {len(changed)}件")
    for raw, b, a in changed:
        print(f"  {raw}: {b} → {a}")
    print(f"normalized の異なり: {len({r['normalized'] for r in rows})}語")


if __name__ == "__main__":
    main()
