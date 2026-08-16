#!/usr/bin/env python3
"""東京都高等学校体育連盟の「大会結果」PDFを取得する。

一覧ページ https://www.tokyo-kotairen.gr.jp/past に、年度ごとの成績一覧PDFが
まとまっている。専門部43サイトを個別に回る必要はない（フォーマットがばらばらで
機械処理に耐えないため、連盟本体が横断集計したこちらを使う）。

対象は既定で直近3年度。古い年度は在校生と関係が薄く、PDFの書式も揺れるため。

⚠️ 取得したPDFには出場生徒の氏名・学年が載っている。本PJでは
   parse_kotairen_results.py が氏名・学年・記録を落として学校単位の実績だけを
   取り出す。PDF自体はリポジトリに含めない（.gitignore）。

出力: data/fetched/kotairen/*.pdf ＋ index.csv（URL・表題・取得日）
"""

from __future__ import annotations

import csv
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "fetched" / "kotairen"
INDEX = "https://www.tokyo-kotairen.gr.jp/past"
UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0          # 要件は2秒以上
DEFAULT_YEARS = 3       # 直近何年度ぶんを取るか


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as res:
        return res.read()


def main() -> None:
    years = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YEARS
    OUT.mkdir(parents=True, exist_ok=True)

    page = get(INDEX).decode("utf-8", "ignore")
    links = [(u, html.unescape(t).strip())
             for u, t in re.findall(r'href="([^"]+\.pdf)"[^>]*>([^<]{2,80})<', page)]
    if not links:
        sys.exit("大会結果PDFのリンクが見つかりません。ページ構成が変わった可能性があります。")

    # 「令和7年度 …」の年度を拾って新しい順に。元号表記が揺れたら拾えたものだけ使う
    def era(label: str) -> int:
        m = re.search(r"令和\s*(元|\d+)\s*年度", label)
        if not m:
            return -1
        return 1 if m.group(1) == "元" else int(m.group(1))

    wanted = sorted({era(t) for _, t in links if era(t) > 0}, reverse=True)[:years]
    targets = [(u, t) for u, t in links if era(t) in wanted]
    print(f"対象: 令和{'・'.join(str(y) for y in wanted)}年度 / {len(targets)}本")

    rows = []
    for i, (url, label) in enumerate(targets, 1):
        name = url.rsplit("/", 1)[-1]
        path = OUT / name
        if path.is_file():
            print(f"  [{i}/{len(targets)}] キャッシュ {name}")
        else:
            print(f"  [{i}/{len(targets)}] 取得 {name} … {label}")
            try:
                path.write_bytes(get(url))
            except Exception as e:                     # 1本落ちても全体は止めない
                print(f"      ⚠ 取得失敗: {e}")
                continue
            time.sleep(INTERVAL)
        rows.append({"file": name, "label": label, "url": url})

    with open(OUT / "index.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "label", "url"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n完了: {len(rows)}本 → {OUT}")


if __name__ == "__main__":
    main()
