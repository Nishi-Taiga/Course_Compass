"""学校座標 × 駅座標 から「学校の最寄駅」と徒歩分を機械的に出せるかの検証。

不動産の徒歩表示は 80m/分（不動産の表示に関する公正競争規約 施行規則）。
直線距離ではなく道なり距離なので、直線 × 1.3 を道なり距離の近似として使う。
"""
import csv, math, collections

S = list(csv.DictReader(open('data/seed/school_coords.csv', encoding='utf-8')))
T = list(csv.DictReader(open('data/seed/stations.csv', encoding='utf-8')))
st = [(r['station_name'], float(r['lat']), float(r['lon'])) for r in T]


def km(a_lat, a_lon, b_lat, b_lon):
    dlat = b_lat - a_lat
    dlon = (b_lon - a_lon) * math.cos(math.radians((a_lat + b_lat) / 2))
    return math.hypot(dlat, dlon) * 111.0


rows = []
for s in S:
    la, lo = float(s['lat']), float(s['lon'])
    best = min(st, key=lambda x: km(la, lo, x[1], x[2]))
    d = km(la, lo, best[1], best[2])
    walk = math.ceil(d * 1.3 * 1000 / 80)          # 道なり近似 → 80m/分
    rows.append({'name': s['name'], 'ward': s['ward'], 'station': best[0],
                 'straight_km': round(d, 2), 'walk_min': walk})

rows.sort(key=lambda r: r['straight_km'])
w = csv.DictWriter(open('data/seed/school_nearest_station.csv',
                        'w', encoding='utf-8', newline=''),
                   fieldnames=['name', 'ward', 'station', 'straight_km', 'walk_min'])
w.writeheader()
w.writerows(rows)

print(f'学校数: {len(rows)}')
b = collections.Counter()
for r in rows:
    b['〜5分' if r['walk_min'] <= 5 else '6〜10分' if r['walk_min'] <= 10
      else '11〜20分' if r['walk_min'] <= 20 else '21分〜'] += 1
for k in ['〜5分', '6〜10分', '11〜20分', '21分〜']:
    print(f'  徒歩{k}: {b[k]}校')
print()
print('最も駅から遠い5校（バス便の可能性が高い＝注記が要る）:')
for r in rows[-5:]:
    print(f"  {r['name']:10s} {r['ward']:6s} 最寄={r['station']:10s} 直線{r['straight_km']}km 徒歩約{r['walk_min']}分")
print()
print('駅至近の5校:')
for r in rows[:5]:
    print(f"  {r['name']:10s} {r['ward']:6s} 最寄={r['station']:10s} 直線{r['straight_km']}km 徒歩約{r['walk_min']}分")
