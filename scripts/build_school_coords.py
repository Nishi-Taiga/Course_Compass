"""国土数値情報 P29「学校」から都立高校の座標を作る。

出典: 「国土数値情報（学校データ）」（国土交通省）2023年度版・CC BY 4.0
      https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html

P29 の属性（2023年度版）
  P29_003 学校分類コード   16004 = 高等学校
  P29_004 名称
  P29_005 所在地
  P29_006 管理者コード     2 = 都道府県立

P29 に無い学校（収録後の新設校）は座標が空のまま出力されるので、
既存の school_coords.csv に値があればそれを引き継ぐ。
"""
import csv, io, json, os, subprocess, sys, zipfile

URL = 'https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_13_GML.zip'
SEED = os.path.join(os.path.dirname(__file__), '..', 'data', 'seed')
OUT = os.path.join(SEED, 'school_coords.csv')


def load_p29():
    blob = subprocess.run(['curl', '-sL', '-m', '180', URL], capture_output=True).stdout
    if blob[:2] != b'PK':
        sys.exit('P29 のダウンロードに失敗しました。URL が変わっていないか確認してください。')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith('.geojson'))
        g = json.loads(z.read(name).decode('utf-8'))

    out = {}
    for f in g['features']:
        p = f['properties']
        if (str(p.get('P29_003')) == '16004' and str(p.get('P29_006')) == '2'
                and str(p.get('P29_004', '')).startswith('東京都立')):
            key = p['P29_004'].replace('東京都立', '').replace('高等学校', '')
            lon, lat = f['geometry']['coordinates']
            out[key] = (round(lat, 6), round(lon, 6))
    return out


def main():
    p29 = load_p29()
    prev = {}
    if os.path.exists(OUT):
        prev = {r['name']: r for r in csv.DictReader(open(OUT, encoding='utf-8'))}

    master = list(csv.DictReader(open(os.path.join(SEED, 'schools_master.csv'), encoding='utf-8')))
    rows, missing = [], []
    for m in master:
        n = m['name']
        if n in p29:
            lat, lon, src = p29[n][0], p29[n][1], 'P29'
        elif n in prev and prev[n]['lat']:
            lat, lon, src = prev[n]['lat'], prev[n]['lon'], prev[n]['source']
        else:
            lat, lon, src = '', '', ''
            missing.append(n)
        rows.append({'school_number': m['school_number'], 'name': n, 'ward': m['ward'],
                     'address': m['address'], 'lat': lat, 'lon': lon, 'source': src})

    with open(OUT, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['school_number', 'name', 'ward', 'address',
                                           'lat', 'lon', 'source'])
        w.writeheader()
        w.writerows(rows)

    got = sum(1 for r in rows if r['lat'])
    print(f'{got}/{len(rows)} 校の座標を書き出しました（P29 収録: {len(p29)} 校）')
    if missing:
        print('座標が取れなかった学校:', missing)
        print('→ P29 の収録後に開校した可能性。新年度版の有無を確認してください。')


if __name__ == '__main__':
    main()
