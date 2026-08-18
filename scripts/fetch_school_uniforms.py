#!/usr/bin/env python3
"""各校公式サイトの「制服・校章・校歌」ページを取得する。

安田の指摘（2026-08-17）を受けた項目。生徒目線では制服の種類
（ブレザー/学ラン/服装自由など）が学校選びの関心事で、都立は
共通CMSの `school_life/symbols.html` にテキストで書かれている。

URLは決め打ちしない。校風ページ（data/fetched/spirit/{slug}.html）の
ナビに「制服」を含むリンクがあるので、そこから実URLを解決する。
決め打ちだと別ホスト5校や構成違いを落とすため（部活ページで実証済み）。

サーバへの配慮は他の fetch_* と同じ: 3秒間隔・UAで名乗る・取得済みスキップ。

出力: data/fetched/uniforms/{slug}.html ＋ _resolved.csv（slug→実URL）
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
SPIRIT = BASE / "data" / "fetched" / "spirit"
OUT = BASE / "data" / "fetched" / "uniforms"
SEED = BASE / "data" / "seed"
UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0

LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>[^<]*制服[^<]*</a>', re.I)


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read()


def main() -> None:
    if not SPIRIT.is_dir():
        sys.exit(f"{SPIRIT} がありません。fetch_school_spirit.py を先に実行してください。")
    OUT.mkdir(parents=True, exist_ok=True)

    sites = list(csv.DictReader(open(SEED / "school_access_sites.csv", encoding="utf-8")))
    resolved, missing = [], []
    fetched = cached = 0

    for i, s in enumerate(sites, 1):
        slug = s["slug"]
        src = SPIRIT / f"{slug}.html"
        if not src.is_file():
            missing.append((slug, "spiritページなし"))
            continue
        raw = src.read_bytes()
        enc = "shift_jis" if re.search(rb'charset=["\']?(shift_jis|sjis)', raw, re.I) else "utf-8"
        m = LINK.search(html.unescape(raw.decode(enc, "ignore")))
        if not m:
            missing.append((slug, "制服リンクなし"))
            continue
        # 相対パスは各校サイトのトップからの絶対URLに直す
        url = urllib.parse.urljoin(f"https://www.metro.ed.jp/{slug}/", m.group(1))
        dest = OUT / f"{slug}.html"
        if dest.is_file():
            cached += 1
        else:
            try:
                dest.write_bytes(get(url))
                fetched += 1
                print(f"  [{i}/{len(sites)}] {s['name']} 取得", flush=True)
            except Exception as e:
                missing.append((slug, f"取得失敗: {e}"))
                continue
            time.sleep(INTERVAL)
        resolved.append({"slug": slug, "school_number": s["school_number"],
                         "name": s["name"], "uniform_url": url})

    with open(OUT / "_resolved.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["slug", "school_number", "name", "uniform_url"])
        w.writeheader()
        w.writerows(resolved)

    print(f"\n取得 {fetched} / キャッシュ {cached} / 解決できず {len(missing)}")
    for slug, why in missing:
        print(f"  ⚠ {slug}: {why}")


if __name__ == "__main__":
    main()
