#!/usr/bin/env python3
"""各校サイトの slug を解決する。

www.metro.ed.jp/sitemap.xml は 210件しか載っておらず、日比谷など**掲載されていない
学校がある**（URL自体は同じ形で生きている）。そこで schools_master.csv の
name_kana からヘボン式ローマ字を起こして slug を推測し、HTTPで存在を確かめる。

slug の作り方（実例で確認）
  マチダソウゴウ -> machidasougou -> machidasogo   （ou -> o）
  ハチオウジキタ -> hachioujikita -> hachiojikita
  ヒビヤ         -> hibiya

出力: data/seed/school_sites.csv（school_number, name, slug, access_url）
"""
import csv
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / 'data' / 'seed'
UA = ('ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; '
      'non-commercial school-guidance project)')

TWO = {'キャ': 'kya', 'キュ': 'kyu', 'キョ': 'kyo', 'シャ': 'sha', 'シュ': 'shu',
       'ショ': 'sho', 'チャ': 'cha', 'チュ': 'chu', 'チョ': 'cho', 'ニャ': 'nya',
       'ニュ': 'nyu', 'ニョ': 'nyo', 'ヒャ': 'hya', 'ヒュ': 'hyu', 'ヒョ': 'hyo',
       'ミャ': 'mya', 'ミュ': 'myu', 'ミョ': 'myo', 'リャ': 'rya', 'リュ': 'ryu',
       'リョ': 'ryo', 'ギャ': 'gya', 'ギュ': 'gyu', 'ギョ': 'gyo', 'ジャ': 'ja',
       'ジュ': 'ju', 'ジョ': 'jo', 'ビャ': 'bya', 'ビュ': 'byu', 'ビョ': 'byo',
       'ピャ': 'pya', 'ピュ': 'pyu', 'ピョ': 'pyo'}
ONE = {'ア': 'a', 'イ': 'i', 'ウ': 'u', 'エ': 'e', 'オ': 'o',
       'カ': 'ka', 'キ': 'ki', 'ク': 'ku', 'ケ': 'ke', 'コ': 'ko',
       'サ': 'sa', 'シ': 'shi', 'ス': 'su', 'セ': 'se', 'ソ': 'so',
       'タ': 'ta', 'チ': 'chi', 'ツ': 'tsu', 'テ': 'te', 'ト': 'to',
       'ナ': 'na', 'ニ': 'ni', 'ヌ': 'nu', 'ネ': 'ne', 'ノ': 'no',
       'ハ': 'ha', 'ヒ': 'hi', 'フ': 'fu', 'ヘ': 'he', 'ホ': 'ho',
       'マ': 'ma', 'ミ': 'mi', 'ム': 'mu', 'メ': 'me', 'モ': 'mo',
       'ヤ': 'ya', 'ユ': 'yu', 'ヨ': 'yo',
       'ラ': 'ra', 'リ': 'ri', 'ル': 'ru', 'レ': 're', 'ロ': 'ro',
       'ワ': 'wa', 'ヲ': 'o', 'ン': 'n',
       'ガ': 'ga', 'ギ': 'gi', 'グ': 'gu', 'ゲ': 'ge', 'ゴ': 'go',
       'ザ': 'za', 'ジ': 'ji', 'ズ': 'zu', 'ゼ': 'ze', 'ゾ': 'zo',
       'ダ': 'da', 'ヂ': 'ji', 'ヅ': 'zu', 'デ': 'de', 'ド': 'do',
       'バ': 'ba', 'ビ': 'bi', 'ブ': 'bu', 'ベ': 'be', 'ボ': 'bo',
       'パ': 'pa', 'ピ': 'pi', 'プ': 'pu', 'ペ': 'pe', 'ポ': 'po',
       'ァ': 'a', 'ィ': 'i', 'ゥ': 'u', 'ェ': 'e', 'ォ': 'o', 'ー': ''}


def romaji(kana):
    out, i = [], 0
    while i < len(kana):
        if kana[i] == 'ッ':
            i += 1
            nxt = TWO.get(kana[i:i + 2]) or ONE.get(kana[i:i + 1], '')
            if nxt:
                out.append(nxt[0])
            continue
        two = TWO.get(kana[i:i + 2])
        if two:
            out.append(two)
            i += 2
            continue
        out.append(ONE.get(kana[i], ''))
        i += 1
    s = ''.join(out)
    s = s.replace('ou', 'o').replace('uu', 'u')     # 長音はヘボン式で詰める
    return re.sub(r'[^a-z]', '', s)


def head(url):
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main():
    known = {}
    sitemap = SEED / 'slugs_sitemap.txt'
    if sitemap.exists():
        known = {s.strip() for s in sitemap.read_text().splitlines() if s.strip()}

    master = list(csv.DictReader(open(SEED / 'schools_master.csv', encoding='utf-8')))
    rows, miss = [], []
    for i, m in enumerate(master, 1):
        base = romaji(m['name_kana'])
        cands = [f'{base}-h', f'{base}-hc', f'{base}-s', f'{base}-he']
        # sitemap に載っているものを最優先で試す
        cands = [c for c in cands if c in known] + [c for c in cands if c not in known]
        hit = None
        for c in cands:
            if c in known:
                hit = c
                break
            if head(f'https://www.metro.ed.jp/{c}/access/access.html') == 200:
                hit = c
                break
            time.sleep(3)
        if hit:
            rows.append({'school_number': m['school_number'], 'name': m['name'],
                         'slug': hit,
                         'access_url': f'https://www.metro.ed.jp/{hit}/access/access.html'})
        else:
            miss.append((m['name'], m['name_kana'], base))
        if i % 25 == 0:
            print(f'  {i}/{len(master)} 解決{len(rows)} 未解決{len(miss)}', flush=True)

    with open(SEED / 'school_sites.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['school_number', 'name', 'slug', 'access_url'])
        w.writeheader()
        w.writerows(rows)
    print(f'\n解決 {len(rows)}/{len(master)}')
    if miss:
        print('未解決（手当てが要る）:')
        for n, k, b in miss:
            print(f'  {n} ({k}) -> {b}')


if __name__ == '__main__':
    main()
