#!/usr/bin/env python3
"""東京都高等学校吹奏楽連盟のコンクール審査結果PDFを取得する。

吹奏楽は都立136校にあり部活データでは最多クラスだが、高体連の管轄外
（高文連系）のため実績が1件も無かった。連盟が審査結果をPDFで公開しており、
学校名・金銀銅・都大会代表がテキストで読める。

結果ページ https://tokousuiren.com/c/competition/com_result/ は
「第66回…【Ａ組】8月10日 8月11日…」のように、回次（年度）と組の見出しの下に
日程ごとのPDFが並ぶ。見出しとの対応が要るので、リンクの前にある文脈から
回次・組を拾ってPDFに紐づける。

出力: data/fetched/suisou/*.pdf ＋ index.csv（回次・組・URL）
"""

from __future__ import annotations

import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "fetched" / "suisou"
INDEX = "https://tokousuiren.com/c/competition/com_result/"
UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0

# 「第66回東京都高等学校吹奏楽コンクール」「【Ａ組】」を見出しとして拾う
KAI = re.compile(r"第\s*(\d+)\s*回東京都高等学校吹奏楽コンクール")
KUMI = re.compile(r"【\s*([ＡＢＣ東日本A-C]+組)\s*】")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as res:
        return res.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page = get(INDEX).decode("utf-8", "ignore")

    # リンクを本文の並び順に見て、直前に現れた見出しを引き継ぐ
    rows, kai, kumi = [], "", ""
    for m in re.finditer(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>|【[^】]*】|第\s*\d+\s*回東京都高等学校吹奏楽コンクール',
                         page, re.I | re.S):
        chunk = html.unescape(m.group(0))
        k = KAI.search(chunk)
        if k and not m.group(1):
            kai = k.group(1)
            continue
        u = KUMI.search(chunk)
        if u and not m.group(1):
            kumi = u.group(1)
            continue
        if not m.group(1):
            continue
        label = re.sub(r"<[^>]+>", "", html.unescape(m.group(2) or "")).strip()
        rows.append({"kai": kai, "kumi": kumi, "label": label,
                     "url": urllib.parse.urljoin(INDEX, m.group(1))})

    if not rows:
        sys.exit("PDFリンクが見つかりません。ページ構成が変わった可能性があります。")

    fetched = cached = 0
    for i, r in enumerate(rows, 1):
        name = f"{r['kai'] or 'x'}_{r['kumi'] or 'x'}_{r['url'].rsplit('/', 1)[-1]}"
        name = re.sub(r"[^\w.-]", "_", name)
        dest = OUT / name
        r["file"] = name
        if dest.is_file():
            cached += 1
            continue
        try:
            dest.write_bytes(get(r["url"]))
            fetched += 1
            print(f"  [{i}/{len(rows)}] 第{r['kai']}回 {r['kumi']} {r['label']}", flush=True)
        except Exception as e:
            print(f"  ⚠ 取得失敗 {r['url']}: {e}")
            r["file"] = ""
            continue
        time.sleep(INTERVAL)

    with open(OUT / "index.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "kai", "kumi", "label", "url"])
        w.writeheader()
        w.writerows([r for r in rows if r.get("file")])

    print(f"\n取得 {fetched} / キャッシュ {cached} / 合計 {len(rows)}本 → {OUT}")


if __name__ == "__main__":
    main()
