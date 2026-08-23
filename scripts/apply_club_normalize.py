#!/usr/bin/env python3
"""西の監修結果を正規化辞書に反映し、school_clubs.normalized を埋める。

監修結果（2026-08-19）
  Q1 男女別 → **分けたまま**。「男子バスケットボール」と「女子バスケットボール」は
     別の部として扱う。合同で活動していない以上、まとめると実態と合わない
  Q2 同好会・班 → **部と同列**に検索へ出す。小山台は部活動全体を「班」と呼ぶため、
     区別すると同校の部活が検索から漏れる
  Q3 表記ゆれ → 誤記と別名は統合する。硬式テニス／ソフトテニスは別物のまま

追加の指示（2026-08-23）
  Q1 の「分けたまま」は**行を分けたまま**という意味で、名前に男女を混ぜる必要は
  なかった。種目名（normalized）と男女（gender）を別の列に分ける。合同でない
  という実態は gender 列がそのまま表しており、「バスケがしたい」に種目名1語で
  当たるようになる（以前は男子・女子の2語が当たり、同じ部が2件に見えていた）。

Q1・Q2 は辞書生成の時点で満たされている。このスクリプトは Q3 の統合を
上乗せし、辞書を school_clubs に反映する。gender 列がまだ無い古い辞書は
ここで種目名から切り出して補う（何度流しても結果は変わらない）。

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
# 硬式テニス／ソフトテニスのように**別物**は入れない
# （男女は名前ではなく gender 列で分けるので、ここには関係しない）。
MERGE = {
    "バトミントン": "バドミントン",       # 誤記
    "ものつくり": "ものづくり",           # 表記ゆれ
    "コンピュータ": "コンピューター",     # 長音の有無
    "バレー": "バレーボール",             # 略称
    "バスケ": "バスケットボール",         # 略称
    "ESS": "英語",                        # 別名（同じ英語系の部）
}


GENDER_PREFIX = ("男女", "男子", "女子")


def split_gender(value: str) -> tuple[str, str]:
    """種目名に男女が混ざっていれば切り出す。gender 列のある辞書では何もしない。"""
    for prefix in GENDER_PREFIX:
        if value.startswith(prefix) and value[len(prefix):]:
            return value[len(prefix):], prefix
    return value, ""


def main() -> None:
    if not DICT.is_file():
        sys.exit(f"{DICT} がありません。")
    rows = list(csv.DictReader(open(DICT, encoding="utf-8")))

    fields = list(rows[0].keys())
    if "gender" not in fields:                       # 古い辞書に列を足す
        fields.insert(fields.index("normalized") + 1, "gender")

    split, changed = [], []
    for r in rows:
        body, gender = split_gender(r["normalized"])
        if gender:
            split.append((r["raw_name"], r["normalized"], body, gender))
        # 既に gender 列がある行はそちらを優先し、無い/空なら切り出した値を入れる
        r["normalized"] = body
        r["gender"] = r.get("gender") or gender

        before = r["normalized"]
        after = MERGE.get(before, before)
        if before != after:
            r["normalized"] = after
            r["decided_by"] = "西の監修(2026-08-19)"
            changed.append((r["raw_name"], before, after))

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"辞書 {len(rows)}行 / 統合した表記 {len(changed)}件")
    for raw, b, a in changed:
        print(f"  {raw}: {b} → {a}")
    if split:
        print(f"種目名から男女を切り出した行 {len(split)}件")
        for raw, b, body, g in split[:5]:
            print(f"  {raw}: {b} → {body} + gender={g}")
    print(f"normalized の異なり: {len({r['normalized'] for r in rows})}語"
          f" / 男女つき {sum(1 for r in rows if r['gender'])}行")


if __name__ == "__main__":
    main()
