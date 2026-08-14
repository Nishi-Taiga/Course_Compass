#!/usr/bin/env python3
"""各校公式サイトの「教育目標・カリキュラム」ページを取得する。

校風は民間の口コミサイトではなく**学校自身の記述**から拾う。
出典を出せること、規約上の懸念が無いこと、そして学校が自分で
どう見られたいかを書いているぶん一次情報として強いこと、が理由。

例（石神井）:
  「チーム石神井で文武二道の両立を！」をスローガンに…
  制服の着用を義務付け、頭髪を染めたり脱色したりすることを禁止し、
  学校全体が生活規律を重視する方向で動いています。

サーバに負荷をかけないための決まりごとは fetch_school_access.py と同じ。
出力: data/fetched/spirit/{slug}.html
"""
import csv
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / 'data' / 'fetched' / 'spirit'
SITES = BASE / 'data' / 'seed' / 'school_sites.csv'
PAGE = 'our_school/education.html'
UA = ('ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; '
      'non-commercial school-guidance project)')
INTERVAL = 3.0


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    if not SITES.is_file():
        sys.exit('school_sites.csv がありません。resolve_school_slugs.py を先に実行してください。')
    OUT.mkdir(parents=True, exist_ok=True)
    sites = list(csv.DictReader(open(SITES, encoding='utf-8')))
    print(f'{len(sites)} 校。3秒間隔で取得します。\n', flush=True)

    ok = skip = ng = 0
    for i, s in enumerate(sites, 1):
        dest = OUT / f"{s['slug']}.html"
        if dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue
        try:
            dest.write_bytes(get(f"https://www.metro.ed.jp/{s['slug']}/{PAGE}"))
            ok += 1
        except urllib.error.HTTPError as e:
            ng += 1
            print(f"  [{i}] {s['name']}({s['slug']}): HTTP {e.code}", flush=True)
        except Exception as e:
            ng += 1
            print(f"  [{i}] {s['name']}({s['slug']}): {e}", flush=True)
        time.sleep(INTERVAL)
        if i % 40 == 0:
            print(f'  {i}/{len(sites)} 取得{ok} 既存{skip} 失敗{ng}', flush=True)

    print(f'\n完了: 取得{ok} 既存{skip} 失敗{ng} → {OUT}')


if __name__ == '__main__':
    main()
