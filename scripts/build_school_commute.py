#!/usr/bin/env python3
"""通学時間を「駅→区」から「駅→学校」に作り直す。

    通学時間 = 鉄道(出発駅 → アクセス起点駅) + アクセス(徒歩 or バス)

アクセス起点駅は学校サイトが挙げた駅を全部持ち、最短のものを採る。
出発地に応じて最適な駅が変わるため（町田総合なら町田・淵野辺・古淵）。

これまでは 647駅 × 49区 の粒度で、同じ区の学校は所要時間が全部同じだった。
練馬区9校はいずれも「新宿から20分」だが、駅からの徒歩だけで7分〜31分の開きがある。

アクセス情報の優先順位:
  1. school_access_verified.csv  目視で確定させたもの（徒歩20分超の学校）
  2. school_access.csv           アクセスページからの自動抽出
  3. school_nearest_station.csv  座標から計算した最寄駅（保険）

出力: data/seed/school_commute_times.csv
"""
import csv
import heapq
import json
import math
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / 'data' / 'raw'
SEED = BASE / 'data' / 'seed'

TRANSFER_MIN = 5.0     # 乗換
BOARD_MIN = 4.0        # 出発時の平均待ち
STOP_MIN = 0.7         # 1駅あたり停車+加減速ロス
SPEED_KMPM = 0.75      # 表定速度 45km/h
AREA_PREF = {11, 12, 13, 14}   # 埼玉・千葉・東京・神奈川。都県境の学校のために4県持つ
MAX_MIN = 120          # これを超える組み合わせは書き出さない


def haversine_km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a['lat'], a['lng'], b['lat'], b['lng']))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def load_speed_factors():
    path = SEED / 'line_speed_factors.csv'
    if not path.exists():
        return {}
    return {int(r['line_code']): float(r['factor'])
            for r in csv.DictReader(open(path, encoding='utf-8'))}


def load_graph():
    stations = {s['code']: s for s in json.loads((RAW / 'station.json').read_text(encoding='utf-8'))}
    factors = load_speed_factors()
    adj = defaultdict(list)
    for f in sorted((RAW / 'lines').glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        ln = d['code']
        sl = [s for s in d.get('station_list', []) if not s.get('closed')]
        fac = factors.get(ln, 1.0)
        for a, b in zip(sl, sl[1:]):
            m = max(1.0, (haversine_km(a, b) / SPEED_KMPM + STOP_MIN) * fac)
            adj[(a['code'], ln)].append(((b['code'], ln), m))
            adj[(b['code'], ln)].append(((a['code'], ln), m))
    by_station = defaultdict(list)
    for (st, ln) in adj:
        by_station[st].append(ln)
    for st, lns in by_station.items():
        for i, l1 in enumerate(lns):
            for l2 in lns[i + 1:]:
                adj[(st, l1)].append(((st, l2), TRANSFER_MIN))
                adj[(st, l2)].append(((st, l1), TRANSFER_MIN))
    return stations, adj, by_station


def dijkstra(origin, adj, by_station):
    dist, best = {}, {}
    pq = [(BOARD_MIN, (origin, ln)) for ln in by_station.get(origin, [])]
    heapq.heapify(pq)
    while pq:
        d, node = heapq.heappop(pq)
        if node in dist:
            continue
        dist[node] = d
        if node[0] not in best:
            best[node[0]] = d
        for nxt, w in adj[node]:
            if nxt not in dist:
                heapq.heappush(pq, (d + w, nxt))
    return best


def load_access():
    """学校ごとの (駅名, 所要分, mode) を集める。確定値を自動抽出より優先。"""
    acc = defaultdict(dict)      # school_number -> {駅名: (分, mode)}

    def put(sn, station, minutes, mode, strong):
        if not station or minutes in ('', None):
            return
        cur = acc[sn].get(station)
        if cur and cur[2] and not strong:
            return               # 確定値が入っていれば自動抽出で上書きしない
        v = int(minutes)
        if cur and cur[0] <= v and bool(cur[2]) == strong:
            return
        acc[sn][station] = (v, mode, strong)

    for path, strong in ((SEED / 'school_access.csv', False),
                         (SEED / 'school_access_verified.csv', True)):
        if not path.exists():
            continue
        for r in csv.DictReader(open(path, encoding='utf-8')):
            put(r['school_number'], r['station'], r['total_min'], r['mode'], strong)

    # 保険: アクセスページから何も取れなかった学校は座標からの最寄駅を使う
    near = {r['name']: r for r in csv.DictReader(
        open(SEED / 'school_nearest_station.csv', encoding='utf-8'))}
    master = list(csv.DictReader(open(SEED / 'schools_master.csv', encoding='utf-8')))
    for m in master:
        if not acc.get(m['school_number']) and m['name'] in near:
            n = near[m['name']]
            acc[m['school_number']][n['station']] = (int(n['walk_min']), 'walk', False)
    return acc, master


def main():
    t0 = time.time()
    stations, adj, by_station = load_graph()
    # 同名駅は「平和台(東京)」のように区別されている。学校サイトの表記に合わせて
    # original_name でも引けるようにし、重複時は東京を優先する。
    name2code = {}
    order = {13: 0, 14: 1, 11: 2, 12: 3}
    for code in sorted(by_station, key=lambda c: order.get(
            stations.get(c, {}).get('prefecture'), 9)):
        s = stations.get(code)
        if s and s.get('prefecture') in AREA_PREF:
            name2code.setdefault(s['name'], code)
            name2code.setdefault(s.get('original_name') or s['name'], code)
    origins = sorted({c for c in by_station
                      if stations.get(c, {}).get('prefecture') == 13})
    print(f'グラフ {len(by_station)}駅 / 出発地(都内) {len(origins)}駅 / {time.time()-t0:.1f}s')

    acc, master = load_access()
    # 駅名 -> code を解決。解決できない駅は落として記録する
    resolved, unresolved = {}, set()
    for sn, opts in acc.items():
        for st in opts:
            if st in name2code:
                resolved.setdefault(st, name2code[st])
            else:
                unresolved.add(st)
    print(f'アクセス起点駅 {len(resolved)} 解決 / {len(unresolved)} 未解決')
    if unresolved:
        print('  未解決:', sorted(unresolved)[:15])

    rows = []
    t1 = time.time()
    for i, o in enumerate(origins, 1):
        best = dijkstra(o, adj, by_station)
        oname = stations[o]['name']
        for sn, opts in acc.items():
            cand = None
            for st, (mins, mode, _strong) in opts.items():
                code = resolved.get(st)
                if code is None:
                    continue
                rail = best.get(code)
                if rail is None:
                    continue
                total = rail + mins
                if cand is None or total < cand[0]:
                    cand = (total, st, mode)
            if cand and cand[0] <= MAX_MIN:
                rows.append({'from_station': oname, 'school_number': sn,
                             'minutes': int(round(cand[0])),
                             'via_station': cand[1], 'access_mode': cand[2]})
        if i % 100 == 0:
            print(f'  {i}/{len(origins)} 駅 ({time.time()-t1:.0f}s)', flush=True)

    out = SEED / 'school_commute_times.csv'
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['from_station', 'school_number', 'minutes',
                                           'via_station', 'access_mode'])
        w.writeheader()
        w.writerows(rows)
    print(f'\n{len(rows):,} 行 → {out} （{time.time()-t0:.0f}s）')
    schools = {r['school_number'] for r in rows}
    print(f'到達できた学校 {len(schools)}/{len(master)}')


if __name__ == '__main__':
    main()
