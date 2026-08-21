#!/usr/bin/env python3
"""日本高校ダンス部選手権（ダンススタジアム）の結果PDFを取得する。

    python3 scripts/fetch_dance_results.py

出力: data/fetched/dance/*.pdf ＋ index.csv

## なぜこのソースなのか

ダンス部は都立144校にあり、文化部では吹奏楽(147)に次ぐ規模。にもかかわらず
実績が**1件も取れていなかった**。理由は管轄で、高体連の70競技にダンスは無く、
高文連にもダンス部門が無い。どちらの連盟にも属さない部活。

この大会は主催が日本ストリートダンス協会・産経新聞社・フジテレビで、
**東京都大会が独立して開催される**。そのため出場校に都立が大量に含まれる
（各年60校以上）。robots.txt は404＝制限なし。

⚠️ このPDFに生徒の氏名は載っていない（学校名だけ）。高野連・演劇と違い、
   氏名を避ける仕掛けは要らない。それでも build 側で検査は通す。

## 取るファイル

  syutsujou_tokyo       東京都大会の出場校        … 都立60校超/年
  syutsujou_junkessyou  全国準決勝の出場校        … **都大会での順位**が入っている
  syutsujou_kessyou     全国決勝の出場校          … 準決勝を勝ち上がった学校
  tokuten_summer_small  全国決勝スモールの得点表  … 全国順位
  tokuten_summer_big    全国決勝ビッグの得点表    … 全国順位

⚠️ 2023年以前はこのURL規則では残っていない（404）。遡れるのは2024年から。
"""

from __future__ import annotations

import csv
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "fetched" / "dance"
UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0
SITE = "https://dancestadium.com/assets/pdf/high/index"

YEARS = [2024, 2025, 2026]
KINDS = {
    "syutsujou_tokyo": "東京都大会 出場校",
    "syutsujou_junkessyou": "全国準決勝 出場校（都大会順位つき）",
    "syutsujou_kessyou": "全国決勝 出場校",
    "tokuten_summer_small": "全国決勝 スモールクラス 得点",
    "tokuten_summer_big": "全国決勝 ビッグクラス 得点",
}


def get(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, fetched, cached, missing = [], 0, 0, 0

    for year in YEARS:
        for kind, label in KINDS.items():
            name = f"{year}_{kind}.pdf"
            dest = OUT / name
            url = f"{SITE}/{year}/{year}{kind}.pdf"
            if dest.is_file():
                cached += 1
            else:
                body = get(url)
                time.sleep(INTERVAL)
                if body is None:
                    missing += 1
                    print(f"  {year} {label}: 公開なし(404)")
                    continue
                dest.write_bytes(body)
                fetched += 1
                print(f"  {year} {label}: 取得 ({len(body) // 1024}KB)", flush=True)
            rows.append({"file": name, "year": str(year), "kind": kind,
                         "label": label, "url": url})

    if not rows:
        sys.exit("1件も取得できませんでした。URLの規則が変わった可能性があります")

    with (OUT / "index.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "year", "kind", "label", "url"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n取得 {fetched} / キャッシュ {cached} / 公開なし {missing}")
    print(f"{(OUT / 'index.csv').relative_to(BASE)} -> {len(rows)}件")


if __name__ == "__main__":
    main()
