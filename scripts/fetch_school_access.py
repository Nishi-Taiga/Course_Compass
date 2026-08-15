#!/usr/bin/env python3
"""各校公式サイトの「アクセス」ページを取得する。

収集元は各校公式サイトのみ。交通案内は学校自身が書いた一次情報なので、
民間の乗換案内より出典として強く、系統名・乗り場・下車停留所まで載っている。

サーバに負荷をかけないための決まりごと（fetch_school_clubs.py と同じ）:
  - robots.txt を起動時に1回だけ読む（2026-08-14時点で Disallow / Crawl-delay とも指定なし）
  - リクエスト間隔は 3秒
  - User-Agent で正直に名乗る
  - 取得済みはスキップする。途中で止まっても再実行すれば続きから進む

出力: data/fetched/access/{slug}.html
"""
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / 'data' / 'fetched' / 'access'
SITEMAP = 'https://www.metro.ed.jp/sitemap.xml'
# HTTPヘッダはASCIIしか通らないので日本語を入れない
UA = ('ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; '
      'non-commercial school-guidance project)')
INTERVAL = 3.0


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def slugs():
    xml = get(SITEMAP).decode('utf-8', 'replace')
    found = re.findall(r'<loc>https://www\.metro\.ed\.jp/([a-z0-9\-]+)/</loc>', xml)
    return sorted(set(found))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        print(get('https://www.metro.ed.jp/robots.txt').decode('utf-8', 'replace').strip())
    except Exception as e:
        sys.exit(f'robots.txt を読めませんでした: {e}')

    ss = slugs()
    print(f'\nslug {len(ss)} 件。3秒間隔で取得します。\n', flush=True)

    ok = skip = ng = 0
    for i, s in enumerate(ss, 1):
        dest = OUT / f'{s}.html'
        if dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue
        try:
            body = get(f'https://www.metro.ed.jp/{s}/access/access.html')
            dest.write_bytes(body)
            ok += 1
        except Exception as e:
            ng += 1
            print(f'  [{i}/{len(ss)}] {s}: {e}', flush=True)
        time.sleep(INTERVAL)
        if i % 25 == 0:
            print(f'  {i}/{len(ss)} 取得{ok} 既存{skip} 失敗{ng}', flush=True)

    print(f'\n完了: 取得{ok} 既存{skip} 失敗{ng} → {OUT}')


if __name__ == '__main__':
    main()
