#!/usr/bin/env python3
"""東京都高等学校演劇コンクール（都大会）の結果を取得して部の実績にする。

    python3 scripts/build_engeki_results.py
    python3 scripts/build_engeki_results.py --offline   # 取得済みHTMLだけで作り直す

出力: data/seed/school_engeki_results.csv
      （school_club_achievements.csv と同じ列）

## 出どころ

都大会は「東京都高等学校文化祭演劇部門中央大会」で、東京都教育委員会と
東京都高等学校文化連盟の共催。結果は東京都高校演劇研究会が記事で公開している。
高文連の部門ページには結果が載っていないため、こちらから取る。

## ⚠️ 個人名を拾わない作り

結果には脚本を書いた生徒の名前が載っている。

    ○東京都高等学校演劇研究会長賞  都立駒場 「焦熱プールサイド」 作：朝倉花野
                                              ~~~~~~~~~~~~~~  ~~~~~~~~~~
                                              作品名（捨てる）  氏名（捨てる）

学校名だけを取り、**学校マスタに載っている名前だけを通す**。作者名は
マスタに存在しないので、この関門を越えられない。伏せ字にするのではなく、
通さないことで守る。
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_clubs import decode_html, text_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
RAW = ROOT / "data" / "fetched" / "engeki"
INDEX_URL = "https://tkek.org/totaikai/"
OUT = SEED / "school_engeki_results.csv"
SOURCE = "東京都高校演劇研究会 都大会 結果"

UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "research use for Tokyo open data hackathon 2026)")
DELAY = 3.0


def get(url: str) -> bytes:
    r = subprocess.run(["curl", "-sS", "-m", "40", "-A", UA, url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200])
    return r.stdout


LINK_RE = re.compile(r'<a[^>]*href="(?P<url>https://tkek\.org/\d{4}/[^"]+)"[^>]*>(?P<t>.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")

# 賞の区切り。「○優秀賞（上演順）」「◇生徒審査員賞」など
AWARD_SPLIT = re.compile(r"[○◯◎◇▽]")
# 「都立駒場 「焦熱プールサイド」」の、カギ括弧の直前にある語＝学校名
BEFORE_TITLE = re.compile(r"([^\s「」／/、。]+)\s*[「『]")


def school_key(name: str) -> str:
    s = re.sub(r"\s+", "", name)
    s = s.replace("東京都立", "").replace("都立", "")
    return re.sub(r"(高等学校|高校)$", "", s)


def parse_article(html: str, master: dict) -> list[tuple[str, str]]:
    """(校名, 賞名) を返す。学校マスタに載っている名前だけを通す。"""
    body = text_of(html)
    # 結果の部分だけを見る。前後の挨拶文に校名が出ることがある
    start = body.find("団体賞")
    if start < 0:
        start = 0
    body = body[start:body.find("＊講師") if "＊講師" in body else len(body)]

    out = []
    for chunk in AWARD_SPLIT.split(body)[1:]:
        # 賞名は、最初の学校が出るまで。「（上演順）」などの但し書きは残す
        m = BEFORE_TITLE.search(chunk)
        if not m:
            continue
        award = re.sub(r"\s+", "", chunk[: m.start(1)]).strip("／/、。 ")
        if not award or len(award) > 60:
            continue
        # ⚠️ 同じ賞の中で同じ学校を2回拾わない。作品名に鉤括弧が入れ子になる
        #   ことがある（「都立昭和高校『駈込み訴え』」）ため、素直に findall
        #   すると同じ学校が二重に出る。
        seen = set()
        for name in BEFORE_TITLE.findall(chunk):
            key = school_key(name)
            if key in master and (key, award) not in seen:
                seen.add((key, award))
                out.append((key, award))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    index_path = RAW / "_index.html"

    if args.offline:
        if not index_path.is_file():
            sys.exit("索引が未取得です。--offline を外して実行してください")
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"索引を取得: {INDEX_URL}")
        index_html = get(INDEX_URL).decode("utf-8", "replace")
        index_path.write_text(index_html, encoding="utf-8")

    articles = []
    seen = set()
    for m in LINK_RE.finditer(index_html):
        title = re.sub(r"\s+", "", TAG.sub("", m.group("t")))
        url = m.group("url")
        if "結果" in title and url not in seen:
            seen.add(url)
            y = re.search(r"(20\d\d)", title) or re.search(r"/(20\d\d)/", url)
            articles.append({
                "title": title, "url": url,
                "year": f"令和{int(y.group(1)) - 2018}年度" if y else "",
            })
    print(f"結果ページ {len(articles)}件")

    master = {r["name"]: r for r in csv.DictReader(
        (SEED / "schools_master.csv").open(encoding="utf-8-sig"))}

    rows = []
    for a in articles:
        dest = RAW / (re.sub(r"[^0-9A-Za-z]+", "_", a["url"])[-60:] + ".html")
        if not dest.exists() or args.force:
            if args.offline:
                continue
            time.sleep(DELAY)
            try:
                dest.write_bytes(get(a["url"]))
            except Exception as ex:
                print(f"  FAIL {a['title']}: {ex}")
                continue
        html = decode_html(dest.read_bytes())
        found = parse_article(html, master)
        print(f"  {a['title'][:30]:32} 都立 {len(found)}校")
        for key, award in found:
            rows.append({
                "school_number": master[key]["school_number"],
                "school": key,
                "year": a["year"],
                "meet": "東京都高等学校文化祭 演劇部門 中央大会（都大会）",
                "sport": "演劇",
                "event": a["title"],
                "division": "",
                "rank": award,
                "source": SOURCE,
            })

    # 同じ学校・同じ大会で複数の賞に載ることがある。全部残す（別々の賞なので）
    rows.sort(key=lambda r: (r["year"], r["school"]))

    # 個人名が混ざっていないか、書き出す前に確かめる
    person = re.compile(r"作：|さん|君|くん")
    leaked = [f"{r['school']} {k}={r[k]}" for r in rows
              for k in ("school", "rank") if person.search(str(r[k]))]
    if leaked:
        print("⚠️ 個人名らしき文字列が含まれています。中止します。")
        for x in leaked[:10]:
            print("   ", x)
        sys.exit(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "school_number", "school", "year", "meet", "sport", "event",
            "division", "rank", "source"])
        w.writeheader()
        w.writerows(rows)

    import collections
    print(f"\n{OUT.relative_to(ROOT)} -> {len(rows)}件 / 都立 {len({r['school'] for r in rows})}校")
    for rank, n in collections.Counter(r["rank"] for r in rows).most_common(10):
        print(f"    {rank[:44]:46} {n}件")


if __name__ == "__main__":
    main()
