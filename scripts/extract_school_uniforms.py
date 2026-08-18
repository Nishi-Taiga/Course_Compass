#!/usr/bin/env python3
"""制服ページ（data/fetched/uniforms/）から、制服の種類と原文を取り出す。

生徒目線の関心（安田 2026-08-17）: ブレザーか学ランか、そもそも制服が
あるのか。加えてページには「スラックス・スカートを選べる」かまで書かれて
いることが多く、これも今の中学生には制服の有無と同等の関心事なので拾う。

方針:
  - 種類は本文の語から機械判定する（ブレザー/学ラン/セーラー/制服なし/標準服）。
    判定できなければ空欄のまま出す。**推測で埋めない**
  - 学校の書いた文をそのまま quote に残す（比べるシートの「学校の言葉」と同じ流儀）
  - 制服の写真は各校の著作物なので取り込まない。リンクで公式ページに誘導する

出力: data/seed/school_uniforms.csv
"""

from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "fetched" / "uniforms"
OUT = BASE / "data" / "seed" / "school_uniforms.csv"

# 種類の判定語。上から順に当て、最初に成立したものを採る
NO_UNIFORM = re.compile(r"制服[はが]?(?:あり|ござい)ません|制服を定めて(?:い|お)りません|私服")
STANDARD = re.compile(r"標準服")
BLAZER = re.compile(r"ブレザー")
GAKURAN = re.compile(r"学ラン|詰襟|詰め襟")
SAILOR = re.compile(r"セーラー")

# スラックス/スカートの選択可。両方の語があり、近くに選択の語があること
CHOICE = re.compile(r"(スラックス|ズボン)[^。]{0,60}スカート|スカート[^。]{0,60}(スラックス|ズボン)")
CHOICE_WORD = re.compile(r"選択|選べ|選ぶ|どちら|いずれ|も可")


def body_text(path: Path) -> str:
    raw = path.read_bytes()
    enc = "shift_jis" if re.search(rb'charset=["\']?(shift_jis|sjis)', raw, re.I) else "utf-8"
    t = html.unescape(re.sub(rb"<script.*?</script>|<style.*?</style>", b"",
                             raw, flags=re.S | re.I).decode(enc, "ignore"))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def uniform_section(text: str) -> str:
    """パンくず以降の「制服」見出しから校章・校歌の手前までを抜く。"""
    crumb = text.find("トップ >")
    i = text.find("制服", crumb if crumb >= 0 else 0)
    if i < 0:
        return ""
    seg = text[i:i + 1200]
    # 先に見出しの繰り返し（「制服・校章・校歌 制服・校章・校歌 制服」）を剥がす。
    # 剥がす前に「校章」で切ると、見出し自身の「校章」に当たって空になる
    seg = re.sub(r"^(制服・校章・校歌\s*)+", "", seg)
    seg = re.sub(r"^制服\s*", "", seg)
    seg = re.sub(r"\s(校章|校歌)(の由来|について)?\s.*$", "", seg)
    return seg.strip()


def classify(seg: str) -> str:
    if NO_UNIFORM.search(seg):
        # 「制服はないが標準服がある」型はこちらが実態
        return "標準服（制服なし）" if STANDARD.search(seg) else "制服なし（服装自由）"
    if BLAZER.search(seg):
        return "ブレザー"
    if GAKURAN.search(seg):
        return "学ラン" + ("・セーラー" if SAILOR.search(seg) else "")
    if SAILOR.search(seg):
        return "セーラー"
    if STANDARD.search(seg):
        return "標準服"
    # 種類は書かれていないが、服の記述や写真見出し（春夏服/秋冬服）はある。
    # 「制服あり」までは言えるが、形は推測しない
    if re.search(r"冬服|夏服|スカート|ズボン|スラックス|ネクタイ|リボン|ワイシャツ|ブラウス|制服", seg):
        return "制服あり（形は公式サイト参照）"
    return ""                       # ページに制服の記述がない。推測しない


def main() -> None:
    resolved = SRC / "_resolved.csv"
    if not resolved.is_file():
        sys.exit("fetch_school_uniforms.py を先に実行してください。")

    rows = []
    for r in csv.DictReader(open(resolved, encoding="utf-8")):
        path = SRC / f"{r['slug']}.html"
        if not path.is_file():
            continue
        seg = uniform_section(body_text(path))
        utype = classify(seg)
        choice = bool(seg and CHOICE.search(seg) and CHOICE_WORD.search(seg))
        # 引用は文の切れ目までの短い一節。書いていない学校は空のまま
        quote = ""
        if seg:
            first = re.split(r"[。！]", seg)[0]
            if 8 <= len(first) <= 160:
                quote = first + "。"
        rows.append({
            "school_number": r["school_number"], "name": r["name"],
            "uniform_type": utype,
            "slacks_skirt_choice": "1" if choice else "",
            "quote": quote,
            "source": r["uniform_url"],
        })

    fields = ["school_number", "name", "uniform_type", "slacks_skirt_choice",
              "quote", "source"]
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    types = Counter(r["uniform_type"] or "（判定できず）" for r in rows)
    print(f"{len(rows)}校 → {OUT}")
    for k, v in types.most_common():
        print(f"  {k}: {v}校")
    print(f"  スラックス/スカート選択可の記述: {sum(1 for r in rows if r['slacks_skirt_choice'])}校")


if __name__ == "__main__":
    main()
