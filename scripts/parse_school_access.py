#!/usr/bin/env python3
"""各校アクセスページから交通案内を取り出す。

方針:
  - 画面に出すのは学校が書いた原文（access_text）。勝手に要約して系統名や
    乗り場番号を落とさない
  - 構造化した station / mode / minutes は「並べ替えと絞り込み」の内部処理用
  - 乗車分が書かれていない学校は minutes を空にする。推定値を入れない

出力:
  data/seed/school_access.csv        構造化（1校に複数行）
  data/seed/school_access_text.csv   原文（1校1行・画面表示用）
"""
import csv
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / 'data' / 'fetched' / 'access'
SEED = BASE / 'data' / 'seed'
RAW = BASE / 'data' / 'raw'

# 交通案内の本文が終わる目印。ここから先はサイト共通のナビゲーション
STOP = ('周辺マップ', '路線図', 'Google Map', 'ニュース アクセス', 'ページの先頭',
        'デジタルブック', '＃だから都立高')
# 交通案内が始まる目印
START = ('路線案内', 'アクセス', '交通', '最寄', '本校まで', '所在地', '住所')


def text_of(path):
    t = path.read_bytes().decode('utf-8', 'replace')
    t = re.sub(r'(?is)<(script|style|head)\b.*?</\1>', ' ', t)
    t = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>', '\n', t)
    t = re.sub(r'(?s)<[^>]+>', ' ', t)
    t = html.unescape(t)
    t = t.replace('　', ' ')
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in t.split('\n')]
    return [l for l in lines if l]


def school_name(lines):
    for l in lines[:80]:
        m = re.search(r'東京都立([^\s　]{1,12}?)(高等学校|中等教育学校)', l)
        if m:
            return m.group(1)
    return None


def transit_block(lines):
    """交通案内らしい範囲を切り出す。ナビゲーションに入ったら止める。"""
    start = None
    for i, l in enumerate(lines):
        if len(l) < 40 and any(k in l for k in START):
            start = i
            break
    if start is None:
        start = 0
    out = []
    for l in lines[start:]:
        if any(k in l for k in STOP):
            break
        out.append(l)
        if len(out) > 60:
            break
    # 駅・バス・徒歩のいずれにも触れない行は落とす（住所や電話番号など）
    keep = [l for l in out if re.search(r'駅|バス|徒歩|下車|乗り場|停留所|線', l)]
    return keep


def gazetteer():
    """1都3県の駅名。長い名前から順に照合する。

    駅データベースは同名駅を「平和台(東京)」「平和台(千葉)」と区別しているが、
    学校サイトは素の「平和台駅」と書く。照合には original_name を使い、
    重複したら東京を優先する。
    """
    st = json.loads((RAW / 'station.json').read_text(encoding='utf-8'))
    order = {13: 0, 14: 1, 11: 2, 12: 3}
    names = {}
    for s in sorted(st, key=lambda x: order.get(x.get('prefecture'), 9)):
        if s.get('prefecture') in (11, 12, 13, 14) and not s.get('closed'):
            names.setdefault(s.get('original_name') or s['name'], s)
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


NUM = r'([0-9０-９]{1,3})'


def z2h(s):
    return unicodedata.normalize('NFKC', s)


def find_station(l, gaz):
    """乗車する駅を拾う。「◯◯駅行き」は行き先なので乗車駅ではない。"""
    def boarding(name):
        for m in re.finditer(r'[「『]?' + re.escape(name) + r'[」』]?\s*駅?', l):
            after = l[m.end():m.end() + 3]
            if re.match(r'\s*(行|方面|ゆき|経由)', after):
                continue          # 行き先表記なので乗車駅ではない
            if re.match(r'\s*線', after):
                continue          # 「有楽町線」「三田線」などの路線名。駅ではない
            return True
        return False

    for name, _ in gaz:
        if len(name) >= 2 and re.search(r'[「『]?' + re.escape(name) + r'[」』]?\s*駅', l) \
                and boarding(name):
            return name
    for name, _ in gaz:
        if len(name) >= 3 and name in l and boarding(name):
            return name
    return None


def scan(lines, gaz):
    """行をなめて (駅, mode, 乗車分, 下車後の徒歩分, 下車停, 原文) を集める。

    交通案内は複数行にまたがる。「JR八王子駅からのご利用」の次の行に
    バスの系統と下車停が書いてある、という書き方が多いので、
    直近に出てきた駅を覚えておいて後続行に結びつける。
    """
    out = []
    cur = None
    bus_section = False          # 「バス」だけの見出し行のあと、続く行もバスの話が続く
    for raw in lines:
        l = z2h(raw)
        if re.fullmatch(r'[【\[]?\s*バス\s*[】\]]?', l):
            bus_section = True
            continue
        if re.fullmatch(r'[【\[]?\s*徒歩\s*[】\]]?', l):
            bus_section = False
            continue
        st = find_station(l, gaz)
        if st:
            cur = st
        if cur is None:
            continue

        # 「下車」は乗り物から降りる語。ただし「◯◯駅下車」は電車を降りる意味なので除く。
        # 野津田のように「（町26）野津田車庫行→神学校下車 徒歩10分」と、
        # バスという語を使わずに系統だけ書く学校がある。これを徒歩と取ると
        # 「町田駅から徒歩10分」という嘘になるので、下車の有無で拾う。
        alight = bool(re.search(r'(?<!駅)下車', l))
        is_bus = bool(re.search(r'バス|のりば|乗り場|停留所|行き\]|】', l)) or alight or (
            bus_section and re.search(r'行き?[、。]|いずれか', l))
        # 「N分」を全部拾い、直前が徒歩なら徒歩、そうでなければ乗車とみなす。
        # 学校ごとに「所要時間約15分」「バスで約7分」「【一之江行き】5分」など
        # 書き方がばらばらなので、語で決め打ちせず位置関係で判定する。
        walk_v = ride_v = None
        walk_is_alt = False
        for m in re.finditer(NUM + r'\s*分', l):
            before = l[max(0, m.start() - 12):m.start()]
            v = int(m.group(1))
            if '徒歩' in before or '歩い' in before:
                if walk_v is None:
                    walk_v = v
                    # 「バスで約7分（徒歩約15分）」の括弧内は下車後の徒歩ではなく
                    # 「歩くなら」という代替手段。足し算してはいけない
                    after = l[m.end():m.end() + 2]
                    walk_is_alt = ('(' in before or '（' in before) and (
                        ')' in after or '）' in after)
            elif '自転車' in before:
                continue
            elif is_bus and ride_v is None:
                ride_v = v
        walk = walk_v
        ride = ride_v
        stop = re.search(r'[「『]([^」』]{1,20})[」』]\s*(?:バス停)?\s*(?:下車|より|から)', l)

        if not is_bus and walk is None:
            continue
        if is_bus:
            if walk_is_alt:
                out.append((cur, 'bus', ride, None, stop.group(1) if stop else '', raw))
                out.append((cur, 'walk', None, walk, '', raw))
            else:
                out.append((cur, 'bus', ride, walk, stop.group(1) if stop else '', raw))
        else:
            out.append((cur, 'walk', None, walk, '', raw))
    return out


def main():
    if not SRC.exists():
        sys.exit(f'{SRC} がありません。先に fetch_school_access.py を実行してください。')
    gaz = gazetteer()
    master = {r['name']: r for r in csv.DictReader(
        open(SEED / 'schools_master.csv', encoding='utf-8'))}

    rows, texts, unmatched = [], [], []
    for f in sorted(SRC.glob('*.html')):
        lines = text_of(f)
        name = school_name(lines)
        if not name or name not in master:
            unmatched.append((f.stem, name))
            continue
        blk = transit_block(lines)
        if not blk:
            continue
        sn = master[name]['school_number']
        url = f'https://www.metro.ed.jp/{f.stem}/access/access.html'
        texts.append({'school_number': sn, 'name': name, 'slug': f.stem,
                      'access_text': '\n'.join(blk), 'source_url': url})
        seen = set()
        for station, mode, ride, walk, stop, detail in scan(blk, gaz):
            key = (station, mode, stop)
            if key in seen:
                continue
            seen.add(key)
            total = ''
            if mode == 'walk':
                total = walk
            elif ride is not None:
                total = ride + (walk or 0)
            rows.append({'school_number': sn, 'name': name, 'station': station,
                         'mode': mode, 'ride_min': ride if ride is not None else '',
                         'walk_min': walk if walk is not None else '',
                         'total_min': total, 'alight_stop': stop,
                         'detail': detail, 'source_url': url})

    with open(SEED / 'school_access.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['school_number', 'name', 'station', 'mode',
                                           'ride_min', 'walk_min', 'total_min',
                                           'alight_stop', 'detail', 'source_url'])
        w.writeheader()
        w.writerows(rows)
    with open(SEED / 'school_access_text.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['school_number', 'name', 'slug',
                                           'access_text', 'source_url'])
        w.writeheader()
        w.writerows(texts)

    schools = {r['school_number'] for r in rows}
    bus = [r for r in rows if r['mode'] == 'bus']
    print(f'ページ {len(list(SRC.glob("*.html")))} / 都立高校として突合 {len(texts)}')
    print(f'アクセス行 {len(rows)} 件・{len(schools)} 校')
    bus_sch = {r['school_number'] for r in bus}
    ride_sch = {r['school_number'] for r in bus if r['ride_min'] != ''}
    print(f'  徒歩 {sum(1 for r in rows if r["mode"]=="walk")} 行 / バス {len(bus)} 行')
    print(f'  バス案内のある学校 {len(bus_sch)} 校、'
          f'うち乗車分が書いてある学校 {len(ride_sch)} 校')
    print(f'  下車バス停が取れたバス行 {sum(1 for r in bus if r["alight_stop"])} / {len(bus)}')
    if unmatched:
        print(f'突合できなかったページ {len(unmatched)} 件（定時制・特別支援など）')


if __name__ == '__main__':
    main()
