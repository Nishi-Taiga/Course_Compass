#!/usr/bin/env python3
"""高校生国際美術展（IFAC）の入賞・佳作PDFを取得する。

美術部136校・書道部は都立に多いが、高体連・高野連・吹奏楽連盟のいずれの
管轄でもなく実績が取れていなかった。この美術展は美術の部と書の部の両方を
公開しており、1つのソースで2つの部をカバーできる。

結果PDFは `/pdf/{回次}_result_art.pdf` `/pdf/{回次}_result_sho.pdf` という
規則的なURL。現行ページには最新回しか載らないが、過去回も同じ規則で残って
いるため回次を遡って取得する（存在しない回は404で自然に止まる）。

⚠️ このPDFには生徒の氏名が載っている。parse 側で学校名だけを読む。

出力: data/fetched/ifac/*.pdf ＋ index.csv
"""

from __future__ import annotations

import csv
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "fetched" / "ifac"
UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0
LATEST = 27          # 第27回（2026年）が最新
BACK = 5             # 何回分さかのぼるか
PARTS = {"art": "美術", "sho": "書道"}


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

    for kai in range(LATEST, LATEST - BACK, -1):
        for key, label in PARTS.items():
            name = f"{kai}_{key}.pdf"
            dest = OUT / name
            url = f"https://www.ihsaf.net/pdf/{kai}_result_{key}.pdf"
            if dest.is_file():
                cached += 1
            else:
                body = get(url)
                time.sleep(INTERVAL)
                if body is None:
                    missing += 1
                    print(f"  第{kai}回 {label}: 公開なし(404)")
                    continue
                dest.write_bytes(body)
                fetched += 1
                print(f"  第{kai}回 {label}: 取得 ({len(body) // 1024}KB)", flush=True)
            rows.append({"file": name, "kai": str(kai), "part": label, "url": url})

    if not rows:
        sys.exit("1本も取得できませんでした。URLの規則が変わった可能性があります。")

    with open(OUT / "index.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "kai", "part", "url"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n取得 {fetched} / キャッシュ {cached} / 未公開 {missing} → {OUT}")


if __name__ == "__main__":
    main()
