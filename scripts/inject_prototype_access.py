#!/usr/bin/env python3
"""プロトタイプの学校データに座標とアクセス情報を足す。

比べるシートに「最寄駅から学校まで」の地図を出すために必要なもの:
  la, lo … 学校の緯度経度（国土数値情報 P29）
  ac     … アクセス起点駅の情報 {st, la, lo, md, mi, dt}
            st=駅名 md=walk|bus mi=所要分(不明ならnull) dt=学校サイトの原文

優先順位は build_school_commute.py と同じ:
  school_access_verified.csv > school_access.csv > school_nearest_station.csv
"""
import csv
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / 'data' / 'seed'
PROTO = BASE / 'prototype' / 'index.html'


def load_station_coords():
    return {r['station_name']: (float(r['lat']), float(r['lon']))
            for r in csv.DictReader(open(SEED / 'stations.csv', encoding='utf-8'))}


def load_raw_station_coords():
    """駅マスタに無い駅（古淵など県外）は駅データベースから引く。"""
    raw = BASE / 'data' / 'raw' / 'station.json'
    if not raw.exists():
        return {}
    out = {}
    order = {13: 0, 14: 1, 11: 2, 12: 3}
    st = json.loads(raw.read_text(encoding='utf-8'))
    for s in sorted(st, key=lambda x: order.get(x.get('prefecture'), 9)):
        if s.get('prefecture') in (11, 12, 13, 14) and not s.get('closed'):
            for key in (s.get('original_name'), s.get('name')):
                if key:
                    out.setdefault(key, (s['lat'], s['lng']))
    return out


def best_access():
    """学校名 -> 最短のアクセス手段。所要分が不明な行も候補に残す。"""
    rows = []
    for path, strong in ((SEED / 'school_access.csv', 0),
                         (SEED / 'school_access_verified.csv', 1)):
        if path.exists():
            for r in csv.DictReader(open(path, encoding='utf-8')):
                r['_strong'] = strong
                rows.append(r)
    best = {}
    for r in rows:
        n = r['name']
        mi = int(r['total_min']) if r['total_min'] else None
        cur = best.get(n)
        # 確定値を優先し、そのなかで所要分が分かるもの・短いものを採る
        rank = (r['_strong'], mi is not None, -(mi if mi is not None else 999))
        if cur is None or rank > cur[0]:
            best[n] = (rank, {'st': r['station'], 'md': r['mode'], 'mi': mi,
                              'dt': r['detail']})
    near = {r['name']: r for r in csv.DictReader(
        open(SEED / 'school_nearest_station.csv', encoding='utf-8'))}
    out = {n: v[1] for n, v in best.items()}
    for n, r in near.items():          # 保険
        out.setdefault(n, {'st': r['station'], 'md': 'walk',
                           'mi': int(r['walk_min']), 'dt': ''})
    return out


def main():
    coords = {r['name']: (float(r['lat']), float(r['lon']))
              for r in csv.DictReader(open(SEED / 'school_coords.csv', encoding='utf-8'))
              if r['lat']}
    # 校風は2つのファイルに分かれている。
    #   school_spirit.csv        本体（決め打ちURLで取れた168校）
    #   school_spirit_extra.csv  そこから漏れた19校。fetch_missing_spirit.py が埋める
    # ⚠️ 後から読むほうを優先する。extra は個別にページを見て決めた出典なので、
    #    本体と重なった場合はそちらのほうが確か。
    spirit = {}
    for sp in (SEED / 'school_spirit.csv', SEED / 'school_spirit_extra.csv'):
        if sp.exists():
            spirit.update({r['name']: r for r in csv.DictReader(open(sp, encoding='utf-8'))})

    stc = load_raw_station_coords()
    stc.update(load_station_coords())      # 駅マスタを優先
    acc = best_access()

    src = PROTO.read_text(encoding='utf-8')
    i = src.index('const D = {')
    j = src.index('};', i) + 1
    D = json.loads(src[i + len('const D = '):j])

    added = miss_coord = miss_station = 0
    for s in D['schools']:
        c = coords.get(s['n'])
        if not c:
            miss_coord += 1
            continue
        s['la'], s['lo'] = round(c[0], 6), round(c[1], 6)
        a = acc.get(s['n'])
        if not a:
            continue
        p = stc.get(a['st'])
        if not p:
            miss_station += 1
            continue
        s['ac'] = {'st': a['st'], 'la': round(p[0], 6), 'lo': round(p[1], 6),
                   'md': a['md'], 'mi': a['mi'], 'dt': a['dt'][:80]}
        added += 1

    # 校風は学校自身の記述をそのまま持つ。判定には使わない
    sp_added = 0
    for s2 in D['schools']:
        r = spirit.get(s2['n'])
        if r and r['spirit']:
            s2['sp'] = r['spirit'][:260]
            s2['spu'] = r['source_url']
            sp_added += 1

    new = src[:i] + 'const D = ' + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + src[j:]
    PROTO.write_text(new, encoding='utf-8')
    print(f'学校 {len(D["schools"])} 件中 アクセス情報を付与 {added} 件 / 校風 {sp_added} 件')
    if miss_coord:
        print(f'  座標が無い学校 {miss_coord} 件')
    if miss_station:
        print(f'  起点駅の座標が引けなかった学校 {miss_station} 件')


if __name__ == '__main__':
    main()
