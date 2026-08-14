#!/usr/bin/env python3
"""駅データベースを取得する（駅間所要時間グラフの入力）。

出典: Seo-4d696b75/station_database (CC BY-SA 4.0)
      https://github.com/Seo-4d696b75/station_database

build_commute_graph.py が data/raw/station.json と data/raw/lines/*.json を読む。
リポジトリには含めない（サイズが大きく、上流で更新されるため）。

注意: 埼玉・千葉・東京・神奈川の1都3県を対象にする。町田・稲城など都県境の
      学校は神奈川の駅（古淵・淵野辺など）が最寄りになるため、東京都だけに
      絞ると最寄駅を取り違える。
"""
import json
import time
import urllib.request
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/Seo-4d696b75/station_database/main/out/main'
RAW = Path(__file__).resolve().parent.parent / 'data' / 'raw'
UA = ('ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; '
      'non-commercial school-guidance project)')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    (RAW / 'lines').mkdir(parents=True, exist_ok=True)

    for name in ('station.json', 'line.json'):
        dest = RAW / name
        if not dest.exists():
            dest.write_bytes(get(f'{BASE}/{name}'))
            print(f'{name} を取得しました')

    lines = json.loads((RAW / 'line.json').read_text(encoding='utf-8'))
    todo = [l for l in lines if not (RAW / 'lines' / f"{l['code']}.json").exists()]
    print(f'路線 {len(lines)} 件（未取得 {len(todo)} 件）')

    for i, l in enumerate(todo, 1):
        dest = RAW / 'lines' / f"{l['code']}.json"
        try:
            dest.write_bytes(get(f"{BASE}/line/{l['code']}.json"))
        except Exception as e:
            print(f"  {l['code']} {l.get('name')}: {e}")
        if i % 100 == 0:
            print(f'  {i}/{len(todo)}', flush=True)
        time.sleep(0.15)

    got = len(list((RAW / 'lines').glob('*.json')))
    print(f'完了: 路線ファイル {got} 件 → {RAW}')


if __name__ == '__main__':
    main()
