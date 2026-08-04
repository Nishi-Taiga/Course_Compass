#!/usr/bin/env python3
"""駅間所要時間の事前計算プロトタイプ。

データ: Seo-4d696b75/station_database (CC BY-SA 4.0)
モデル: 路線を意識したダイクストラ。
  - ノード = (駅code, 路線code)
  - 乗車エッジ = 同一路線の隣接駅間。所要時間 = 駅間距離(km) / 表定速度 + 停車時間
  - 乗換エッジ = 同一駅の別路線間 5分
  - 出発ペナルティ = 初乗り待ち 4分(平均運転間隔の半分の粗い近似)
仕様書§6.3のフォールバック(駅間1.5分固定)より一段精密な距離ベース概算。
出力粒度はレンジ表示(30-45分等)前提なのでこの精度で成立する。
"""
import json
import math
import heapq
import time
from pathlib import Path
from collections import defaultdict

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

TRANSFER_MIN = 5.0     # 乗換
BOARD_MIN = 4.0        # 出発時の平均待ち
STOP_MIN = 0.7         # 1駅あたり停車+加減速ロス
SPEED_KMPM = 0.75      # 表定速度 45km/h = 0.75km/分 (都市部在来線の粗い平均)
AREA_PREF = {11, 12, 13, 14}


def haversine_km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def load_graph():
    """(駅,路線)ノードの隣接リストと駅メタを返す。"""
    stations = {s["code"]: s for s in json.load(open(RAW / "station.json"))}
    adj = defaultdict(list)  # (st,ln) -> [((st2,ln2), minutes)]
    lines_loaded = 0
    for f in sorted((RAW / "lines").glob("*.json")):
        d = json.load(open(f))
        ln = d["code"]
        sl = [s for s in d["station_list"] if not s.get("closed")]
        lines_loaded += 1
        for a, b in zip(sl, sl[1:]):
            km = haversine_km(a, b)
            minutes = max(1.0, km / SPEED_KMPM + STOP_MIN)
            adj[(a["code"], ln)].append(((b["code"], ln), minutes))
            adj[(b["code"], ln)].append(((a["code"], ln), minutes))
    # 乗換エッジ: 同一駅codeの別路線ノード間
    by_station = defaultdict(list)
    for (st, ln) in adj:
        by_station[st].append(ln)
    for st, lns in by_station.items():
        for i, l1 in enumerate(lns):
            for l2 in lns[i + 1:]:
                adj[(st, l1)].append(((st, l2), TRANSFER_MIN))
                adj[(st, l2)].append(((st, l1), TRANSFER_MIN))
    return stations, adj, by_station, lines_loaded


def dijkstra_from(origin_code, adj, by_station):
    """出発駅から全駅への所要分。返り値: {駅code: 分}"""
    dist = {}
    pq = []
    for ln in by_station.get(origin_code, []):
        heapq.heappush(pq, (BOARD_MIN, (origin_code, ln)))
    best_station = {}
    while pq:
        d, node = heapq.heappop(pq)
        if node in dist:
            continue
        dist[node] = d
        st = node[0]
        if st not in best_station:
            best_station[st] = d
        for nxt, w in adj[node]:
            if nxt not in dist:
                heapq.heappush(pq, (d + w, nxt))
    return best_station


def main():
    t0 = time.time()
    stations, adj, by_station, nlines = load_graph()
    active = [c for c in by_station if stations.get(c, {}).get("prefecture") in AREA_PREF]
    tokyo = [c for c in by_station if stations.get(c, {}).get("prefecture") == 13]
    print(f"graph: {nlines} lines, {len(by_station)} stations in graph "
          f"({len(tokyo)} in Tokyo), {sum(len(v) for v in adj.values())} directed edges, "
          f"build {time.time()-t0:.1f}s")

    # サニティチェック（実勢: 練馬→渋谷 実乗車20-25分+乗換)
    name2code = {}
    for c in by_station:
        s = stations.get(c)
        if s:
            name2code.setdefault(s["name"], c)
    checks = [("練馬", "渋谷"), ("練馬", "日比谷"), ("八王子", "新宿"),
              ("町田", "渋谷"), ("北千住", "品川"), ("吉祥寺", "上野")]
    t1 = time.time()
    for o, d in checks:
        if o in name2code and d in name2code:
            res = dijkstra_from(name2code[o], adj, by_station)
            v = res.get(name2code[d])
            print(f"  {o} -> {d}: {v:.0f}分" if v else f"  {o} -> {d}: 到達不可")
    print(f"6 origins dijkstra: {time.time()-t1:.2f}s")

    # フル事前計算の見積り: 東京都全駅を出発地に
    t2 = time.time()
    n = 0
    for c in tokyo[:50]:
        dijkstra_from(c, adj, by_station)
        n += 1
    per = (time.time() - t2) / n
    print(f"per-origin: {per*1000:.0f}ms -> 都内{len(tokyo)}駅全出発地で約{per*len(tokyo):.0f}s")


if __name__ == "__main__":
    main()
