#!/usr/bin/env python3
"""教育目標ページから校風の記述を取り出す。

方針:
  - **学校自身の言葉をそのまま**残す。要約も言い換えもしない
  - 判定・並べ替えには一切使わない。「学校を知る手がかり」として見せるだけ
  - 口コミサイトは使わない（規約の懸念があり、そもそも出典を出せない）

出力: data/seed/school_spirit.csv
  motto  … 教育目標にあたる短い行（箇条書きで並んでいることが多い）
  spirit … 学校が自分の校風を説明している段落のうち最も長いもの
"""
import csv
import html
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / 'data' / 'fetched' / 'spirit'
# 教育目標ページがPDF頼りで本文を持たない学校のための2つ目の出典（特色ページ）
SRC2 = BASE / 'data' / 'fetched' / 'spirit2'
SEED = BASE / 'data' / 'seed'

# ここから先はサイト共通のナビゲーション
NAV = ('ニュース アクセス', 'ページの先頭', '＃だから都立高', '東京都立学校一覧',
       'デジタルブック', '在校生・保護者の方へ', '卒業生の方へ', 'メインメニュー',
       'このサイトではJavaScript', '本文へ移動')


def main_text(path):
    t = path.read_bytes().decode('utf-8', 'replace')
    m = re.search(r'(?is)id=[\'"]mainContents[\'"](.*)', t)
    seg = m.group(1) if m else t
    seg = re.sub(r'(?is)<(script|style).*?</\1>', ' ', seg)
    seg = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td)>', '\n', seg)
    seg = re.sub(r'(?s)<[^>]+>', ' ', seg)
    seg = html.unescape(seg).replace('　', ' ')
    out = []
    for l in seg.split('\n'):
        l = re.sub(r'[ \t]+', ' ', l).strip()
        if not l:
            continue
        if any(k in l for k in NAV):
            if out:
                break
            continue
        if l.startswith('トップ >') or l.startswith('class='):
            continue
        out.append(l)
    return out


# 卒業生・在校生の体験談。学校の校風説明ではないので校風として出してはいけない
VOICE = re.compile(r'私は|私が|僕は|わたしは|入学当初|卒業生の声|在校生の声|先輩の声|'
                   r'でした。私|と思います。私')
# 学校が自分を説明している段落に出てくる語
SCHOOLY = re.compile(r'本校|当校|生徒|教育|育成|指導|校風|学習|部活|行事|伝統|校訓|'
                     r'精神|自由|自主|responsib|人間|態度|力を|心を|養う|重んじ|守る|'
                     r'目指|めざす|大切')
# 見出し・添付ファイル・準備中など、校風の記述ではない行
NOISE = re.compile(
    r'PDF\s*\(|\(\s*[0-9．.]+\s*[KMk]B|年間授業計画|グランドデザイン$|'
    r'^教育目標(・|$)|^カリキュラム|^準備中|^スクール[・\s]|^東京都立|'
    r'^[0-9０-９]{2,3}【|シラバス|一覧$|^>+$|'
    # サイト共通のナビゲーション項目。校風の記述ではない
    r'^進路指導|^学校の様子|^学校行事$|^部活動|^入試案内|^学校説明会|^在校生|^卒業生|'
    r'^教育課程|^制服・校章|^沿革$|^学校運営方針|^災害時|^Ｑ＆Ａ|^Q&A|^図書|^奨学金|'
    r'^模擬試験|^探究活動|^企業の皆様|^支援制度|^応募状況|^学力検査問題')


def looks_like_description(l):
    if VOICE.search(l) or NOISE.search(l):
        return False
    # 区切り線や記号だけの行を弾く
    jp = len(re.findall(r'[぀-ヿ一-鿿]', l))
    if jp < len(l) * 0.4:
        return False
    return bool(SCHOOLY.search(l))


def pick(lines):
    """短い行＝教育目標、長い段落＝校風の説明、として拾う。"""
    # 日比谷・青山のように、長い段落を持たず40字前後の箇条書きで書く学校がある
    body = [l for l in lines if len(l) >= 38 and looks_like_description(l)]
    short = [l for l in lines
             if 6 <= len(l) <= 46 and not re.match(r'^[０-９0-9]+[\.．]?$', l)
             and not VOICE.search(l)
             and not re.match(r'^(教育目標|学校の教育目標|カリキュラム)', l)]
    spirit = max(body, key=len) if body else ''
    if spirit and len(spirit) < 90 and len(body) > 1:
        # 1文だけでは校風が伝わらないので、上位2文をつなぐ
        top = sorted(body, key=len, reverse=True)[:2]
        spirit = ' '.join(sorted(top, key=lines.index))
    if not spirit:
        # 戸山・北園のように、長い段落を持たず短い箇条書きだけで書く学校がある。
        # 「自分の行動に責任をもつ。」「学校生活にふさわしい身なりを心がける。」など
        # 1行は短くても、並べれば校風が伝わる。出てきた順につないで1本にする。
        bullets = [l for l in lines
                   if 10 <= len(l) < 38 and looks_like_description(l)]
        buf = []
        for b in bullets:
            if sum(len(x) for x in buf) + len(b) > 200:
                break
            if b not in buf:
                buf.append(b)
        if len(buf) >= 2:
            spirit = '　'.join(buf)
    # 校則・生活指導に触れている段落があればそちらを優先する（保護者の関心が高い）
    for b in body:
        if re.search(r'制服|頭髪|校則|生活指導|規律|服装', b):
            spirit = b
            break
    motto = ' ／ '.join(short[1:5]) if len(short) > 1 else (short[0] if short else '')
    return motto[:120], spirit[:400]


def main():
    if not SRC.exists():
        sys.exit(f'{SRC} がありません。先に fetch_school_spirit.py を実行してください。')
    sites = {r['slug']: r for r in csv.DictReader(
        open(SEED / 'school_sites.csv', encoding='utf-8'))}

    rows, empty = [], []
    for f in sorted(SRC.glob('*.html')):
        s = sites.get(f.stem)
        if not s:
            continue
        motto, spirit = pick(main_text(f))
        page = 'education'
        if not spirit:
            alt = SRC2 / f.name
            if alt.exists():
                motto, spirit = pick(main_text(alt))
                page = 'feature'
        if not spirit:
            empty.append(s['name'])
            continue
        rows.append({'school_number': s['school_number'], 'name': s['name'],
                     'motto': motto, 'spirit': spirit,
                     'source_url': f"https://www.metro.ed.jp/{f.stem}/our_school/{page}.html"})

    with open(SEED / 'school_spirit.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['school_number', 'name', 'motto',
                                           'spirit', 'source_url'])
        w.writeheader()
        w.writerows(rows)
    print(f'ページ {len(list(SRC.glob("*.html")))} / 校風を取れた学校 {len(rows)}')
    print(f'  校則・生活指導に触れている学校 '
          f'{sum(1 for r in rows if re.search("制服|頭髪|校則|規律|服装", r["spirit"]))}')
    if empty:
        print(f'  本文が取れなかった学校 {len(empty)}: {empty[:8]}')


if __name__ == '__main__':
    main()
