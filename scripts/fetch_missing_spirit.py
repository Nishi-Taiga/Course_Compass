#!/usr/bin/env python3
"""校風（学校の言葉）が取れていない学校を、公式サイトから個別に埋める。

    python3 scripts/fetch_missing_spirit.py

出力: data/fetched/spirit3/*.html ＋ data/seed/school_spirit_extra.csv

## なぜ別スクリプトなのか

本体の fetch_school_spirit.py は school_access_sites.csv の slug を使い、
`https://www.metro.ed.jp/{slug}/our_school/education.html` という
決め打ちのURLを取りに行く。この形に**当てはまらない学校が21校**あり、
比べるシートの「学校の言葉」がずっと空欄のままだった。

  独自ドメイン   八潮 yashio-h.metro.ed.jp / 広尾 hiroo-h.metro.ed.jp …
  課程で枝分かれ 六郷工科 /zen/zennichi.html 五日市 /zen/
  そもそも別法人 産業技術高専（品川・荒川）は metro-cit.ac.jp

決め打ちを増やすと同じことの繰り返しになるので、**トップページから
教育目標ページへのリンクを辿る**形にした。

## 決まりごと

3秒間隔・正直なUser-Agent。fetch_school_access.py と同じ。
本文の取り出しは parse_school_spirit.py の関数をそのまま使う
（同じ基準で拾わないと、この21校だけ毛色の違う文章が混ざる）。
"""

from __future__ import annotations

import csv
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_school_spirit import main_text, pick  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
OUT = BASE / "data" / "fetched" / "spirit3"
SITES = SEED / "school_sites.csv"
SPIRIT = SEED / "school_spirit.csv"
MASTER = SEED / "schools_master.csv"
DEST = SEED / "school_spirit_extra.csv"

UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "non-commercial school-guidance project)")
INTERVAL = 3.0

# ⚠️ リンクを辿っても届かない学校。実際にサイトを見て、ページを直に指定した。
#    トップのナビが画像・フレーム・言語選択で、<a> の文言から辿れないものが多い。
OVERRIDE = {
    # 別法人（都教委のサイトに載らない）。品川・荒川は同じ法人の2キャンパス
    "産業技術高専（品川）": "https://www.metro-cit.ac.jp/information/philosophy.html",
    "産業技術高専（荒川）": "https://www.metro-cit.ac.jp/information/philosophy.html",
    # トップが日本語/English の選択だけで、教育目標は言語別サイトの下にある
    "国際": "https://kokusai-h.metro.ed.jp/principal/education.html",
    # トップが全日制/定時制のフレーム。ナビは about_school.html にしか出てこない
    "六郷工科": "https://rokugokoka-h.metro.ed.jp/zen/about_school.html",
    # CMS製。カテゴリ一覧は中身が空で、記事ページを直に指す必要がある
    "八潮": "https://yashio-h.metro.ed.jp/site/zen/page_0000000_00015.html",
}

# ⚠️ どうしても取れなかった学校。追いかけた経緯を残す。
#
#   広尾     本文が外部CMS（pweb.jp）の iframe 内にあり、JavaScript を
#            動かさないと中身が出てこない。校長あいさつのページは辿れるが、
#            そこに書いてあるのは「日頃から御理解と御協力を…」の定型句だけ。
#   六郷工科 サイトに教育目標にあたるページが存在しない。about_school.html は
#            見出しだけの2.8KBで本文を持たず、全日制・定時制のどちらの側にも
#            該当ページが無い（実際に辿って確認した）。
#
# 無理に何かを載せるより、空欄のままにする。学校の言葉は**学校自身の記述**を
# そのまま出す欄なので、別のページの文章で埋めると欄の意味が変わってしまう。
UNAVAILABLE = ("広尾", "六郷工科")

# トップページから辿る先。上にあるものほど校風が書かれている見込みが高い
LINK_WORDS = [
    "教育目標", "教育理念", "スクールミッション", "school_mission",
    "本校の特色", "学校の特色", "特色", "学校概要", "学校紹介",
    "校長挨拶", "校長あいさつ", "教育方針", "our_school",
]
# 決め打ちで当たることが多いので、リンク探しの前に試す
DIRECT = ["our_school/education.html", "our_school/index.html"]


# --- 拾った文の選び直し ---------------------------------------------------
#
# ⚠️ この21校は「学校経営計画」をそのまま教育目標ページに載せている学校が多く、
#    parse_school_spirit.py の基準だけでは校内向けの施策が混ざる。実際に出た例:
#
#      ①全教職員による組織的な朝の立番等によるマナー指導及び遅刻・服装指導…
#      ウ 人間としての在り方・生き方について深く学び…
#      浅学菲才にして甚だ微力ではありますが、本校の発展のために…
#
#    保護者が読む「学校の言葉」としては、どれも学校を知る手がかりにならない。
#    本体の parse 側を触ると既存168校の文面まで変わってしまうため、
#    **ここで拾い直す**。同じ pick() に、掃除した行を渡す形にしてある。

# 行頭の番号・記号。「コ 言語活動を…」のような単独カナの見出しも落とす
ENUM = re.compile(r"^\s*(?:[①-⑳]|[（(]\s*[0-9０-９]+\s*[)）]|[ア-ン]\s+|[0-9０-９]+[.．)）]\s*)")
# 校内向けの施策・校長挨拶の定型句。学校の校風の説明ではない
PLAN = re.compile(r"全教職員|立番|授業時数を確保|意図的・計画的|周知徹底|"
                  r"浅学菲才|微力|所存|着任|よろしくお願い|ホームページをご覧|御理解と御協力|ご理解とご協力|ありがとうございます|申し上げます")
# 文末に紛れ込む組織名
ORGJUNK = re.compile(r"^(一般)?財団法人|^学校法人|^東京都教育委員会$|教育財団$")
# パンくず・共通の注意書き。素朴版の取り出しはこれらを落とさないので、ここで落とす
CRUMB = re.compile(r"^(トップ|ホーム)\s*[>＞»]|[>＞]\s*(学校案内|教育目標)|JavaScript|Copyright|©|このサイトでは")


def complete(line: str) -> bool:
    """長い行は、言い切っているものだけを使う。

    ⚠️ ページの途中で切れた断片が混ざる（広尾の「理想的な教育環境を実現してい」）。
       短い箇条書きは「…人間を育てる」で終わるのが普通なので、長い行にだけ課す。
    """
    return len(line) < 38 or bool(re.search(r"[。．！？」』]$", line.strip()))


def refine(lines: list[str]) -> list[str]:
    out = []
    for l in lines:
        l = ENUM.sub("", l).strip()
        if not l or PLAN.search(l) or ORGJUNK.search(l) or CRUMB.search(l) or not complete(l):
            continue
        out.append(l)
    return out


def get(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def find_links(html: bytes, base_url: str) -> list[str]:
    """トップページから、校風が書いてありそうなページへのリンクを拾う。"""
    text = html.decode("utf-8", "replace")
    found: list[tuple[int, str]] = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>',
                         text, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        blob = f"{href} {label}"
        for rank, word in enumerate(LINK_WORDS):
            if word in blob:
                found.append((rank, urllib.parse.urljoin(base_url, href)))
                break
    # 順位が上のものから、重複を除いて返す
    seen, out = set(), []
    for _, url in sorted(found, key=lambda x: x[0]):
        if url not in seen and not url.lower().endswith((".pdf", ".jpg", ".png")):
            seen.add(url)
            out.append(url)
    return out[:4]


def main() -> None:
    master = {r["name"]: r for r in csv.DictReader(MASTER.open(encoding="utf-8-sig"))}
    have = {r["name"] for r in csv.DictReader(SPIRIT.open(encoding="utf-8-sig"))
            if (r["spirit"] or "").strip()}
    sites = {r["name"]: r for r in csv.DictReader(SITES.open(encoding="utf-8-sig"))}

    # 埋めたい学校＝マスタにあって校風が無いもの ＋ 高専
    targets: dict[str, str] = {}
    for name in list(master) + list(OVERRIDE):
        if name in have or name in UNAVAILABLE:
            continue
        url = OVERRIDE.get(name) or (sites.get(name) or {}).get("top_url")
        if url:
            targets[name] = url
        else:
            print(f"  {name}: トップページのURLが分かりません")

    if not targets:
        print("埋めるべき学校はありません")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(targets)} 校。3秒間隔で取得します。\n", flush=True)
    rows, ng = [], []

    for i, (name, top) in enumerate(sorted(targets.items()), 1):
        slug = re.sub(r"[^\w]", "_", name)
        dest = OUT / f"{slug}.html"
        page_url = ""

        if dest.is_file() and dest.stat().st_size > 0:
            page_url = (OUT / f"{slug}.url").read_text(encoding="utf-8").strip()
        else:
            # ① 決め打ちのパス ② トップページから辿る、の順で当てる
            if name in OVERRIDE:
                candidates = [top]          # 見て決めたページ。探し直さない
            else:
                candidates = [urllib.parse.urljoin(top, d) for d in DIRECT]
                body = get(top)
                time.sleep(INTERVAL)
                if body:
                    candidates += find_links(body, top)
            for url in candidates:
                page = get(url)
                time.sleep(INTERVAL)
                if not page:
                    continue
                motto, spirit = pick(refine(main_text_from(page)))
                if spirit:
                    dest.write_bytes(page)
                    (OUT / f"{slug}.url").write_text(url, encoding="utf-8")
                    page_url = url
                    break

        if not page_url:
            ng.append(name)
            print(f"  [{i}] {name}: 校風の記述が見つかりませんでした", flush=True)
            continue

        motto, spirit = pick(refine(main_text_from(dest.read_bytes())))
        if not spirit:
            ng.append(name)
            continue
        rows.append({
            "school_number": (master.get(name) or {}).get("school_number", ""),
            "name": name, "motto": motto, "spirit": spirit, "source_url": page_url,
        })
        print(f"  [{i}] {name}: {spirit[:38]}…", flush=True)

    if not rows:
        sys.exit("1件も取れませんでした")

    with DEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["school_number", "name", "motto",
                                          "spirit", "source_url"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n{DEST.relative_to(BASE)} -> {len(rows)}件 / 取れなかった {len(ng)}件")
    if ng:
        print("  " + "・".join(ng))


def plain_text(body: bytes) -> list[str]:
    """タグを落とすだけの素朴な本文取り出し。

    ⚠️ parse_school_spirit.main_text は id="mainContents" を前提にし、
       「アクセス」「ページの先頭」などのナビ語が出た時点で本文を打ち切る。
       都教委の共通テンプレートを使っていない学校（国際・八潮など）では、
       この打ち切りが本文の手前で起きてタイトル1行しか残らない。
       そういう学校のための逃げ道。
    """
    t = body.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td|dd|dt)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    import html as _html
    t = _html.unescape(t).replace("\u3000", " ")
    return [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n") if l.strip()]


def main_text_from(body: bytes) -> list[str]:
    """main_text はパスを取るので、バイト列から使えるようにする薄い包み。

    共通テンプレート向けの取り出しで足りなければ、素朴版に落とす。
    """
    tmp = OUT / "_tmp.html"
    tmp.write_bytes(body)
    try:
        lines = main_text(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    if sum(1 for l in lines if len(l) >= 30) >= 2:
        return lines
    return plain_text(body)


if __name__ == "__main__":
    main()
