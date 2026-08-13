#!/usr/bin/env python3
"""各校の公式サイトURLと部活動ページURLを解決して data/seed/school_sites.csv を作る。

    python3 scripts/build_school_sites.py            # 未取得のトップページだけ取得して生成
    python3 scripts/build_school_sites.py --offline  # 取得済みHTMLだけで生成し直す（通信なし）
    python3 scripts/build_school_sites.py --force    # トップページを取り直す

Step6（部活190校バッチ）の前段。fetch_school_clubs.py は school_sites.csv の
clubs_url を読むだけなので、その台帳をここで作る。

## 一次ソース

東京都立学校ポータル（https://www.metro.ed.jp/）が「五十音順一覧」の
ダウンロード用に配っている **都立高校一覧の XLSX**。

    https://www.metro.ed.jp/js/xlsx/list.xlsx

学校ID・学校名・ふりがな・課程・所在地・URL が1行1課程で入っている。
sitemap.xml も試したが、**日比谷を含む複数校が載っておらず**、
別ホストの学校（国際・広尾など）も拾えないため採用しない。

この一覧を使う利点:

  - **課程が列で分かる**。全日制だけを機械的に選べる（title の文字列判定が要らない）
  - **URLが列で入っている**。slug のローマ字を推測しなくてよい
    （芝商業が sibasyogyo、桑志が soushi のように訓令式・ヘボン式が混在する）
  - 5校は別ホスト（yashio-h / kokusai-h / rokugokoka-h / hiroo-h / itsukaichi-h）に
    あり、パスも /site/zen/ や /zen/zennichi.html と揃っていない。URL列ならこれも拾える

マスタとの突き合わせは**校名**で行う。XLSXの学校IDは大半がマスタの学校番号と
一致する（7401020 → 401020）が、日本橋・八王子北など一致しない行があり、
ID列が空の行もあるため、IDは裏取りにだけ使って食い違いは警告として残す。

## 対象校

全日制のみ（167校）。以下はこの時点で対象外になる:

  - 定時制・通信制のみの学校 … MVPの検索は全日制だけを見ている
  - 中等教育学校、高校からの募集停止校（富士・大泉・白鴎・両国・武蔵）
    … 一覧上で課程が空欄になっており、全日制の絞り込みで自然に外れる

取得したHTMLは data/fetched/tops/ に残す。発見の規則を直すたびにサーバを
叩き直さないため（robots.txt は守っているが、それとは別に礼儀の問題）。
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_school_clubs import (  # noqa: E402
    DEFAULT_DELAY_SEC,
    USER_AGENT,
    Crawler,
    fetch,
)

ROOT = Path(__file__).resolve().parent.parent
MASTER_CSV = ROOT / "data" / "seed" / "schools_master.csv"
TOPS_DIR = ROOT / "data" / "fetched" / "tops"
LIST_XLSX = ROOT / "data" / "fetched" / "metro_school_list.xlsx"
OUT_CSV = ROOT / "data" / "seed" / "school_sites.csv"
PROBLEMS_CSV = TOPS_DIR / "_problems.csv"

LIST_URL = "https://www.metro.ed.jp/js/xlsx/list.xlsx"
SOURCE_LABEL = "東京都立学校ポータル 都立高校一覧(list.xlsx)"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# ------------------------------------------------------------ XLSX 読み取り

def _shared_string(si: ET.Element) -> str:
    """<si> の文字列。ルビ（<rPh>）は本文ではないので拾わない。

    拾ってしまうと「八潮高等学校ヤシオコウ」のようにカナが混ざり、校名照合が落ちる。
    """
    parts = []
    for el in si:
        tag = el.tag[len(NS):]
        if tag == "t":
            parts.append(el.text or "")
        elif tag == "r":                      # 書式が変わる箇所で分割された本文
            parts.extend(t.text or "" for t in el.findall(NS + "t"))
    return "".join(parts)


def read_school_list(blob: bytes) -> list[dict[str, str]]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = [_shared_string(si)
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(NS + "si")]

    rows: list[dict[str, str]] = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(NS + "row"):
        cells: dict[str, str] = {}
        for c in row.findall(NS + "c"):
            col = re.match(r"([A-Z]+)", c.get("r") or "A").group(1)
            v = c.find(NS + "v")
            if v is None or v.text is None:
                cells[col] = ""
            elif c.get("t") == "s":
                cells[col] = shared[int(v.text)].strip()
            else:
                cells[col] = v.text.strip()
        rows.append(cells)

    header, *body = rows
    keys = {"school_id": "B", "name": "D", "kana": "E",
            "course": "F", "address": "G", "ward": "H", "url": "I"}
    if header.get("D") != "学校名" or header.get("I") != "URL":
        sys.exit(f"list.xlsx の列構成が変わっています: {header}")

    return [{k: r.get(col, "") for k, col in keys.items()} for r in body if r.get("I")]


# ---------------------------------------------------------- 部活ページ発見

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")

# 記事アーカイブ（/activities/2026/08/clubentry_26.html 等）は個別記事なので、
# ここから部活の全体像は取れない。一覧ページだけを拾いたい。
ARTICLE_RE = re.compile(r"/(19|20)\d{2}/\d{1,2}/")

TEXT_STRONG = ("部活動", "部活", "同好会", "クラブ活動")
TEXT_WEAK = ("生徒会", "学校生活", "課外活動")
URL_HINTS = ("activities", "activity", "bukatsu", "club", "katsudo", "kurabu", "seitokai")

# 言語選択などの入口ページ対策。国際高校のトップは「日本語サイト / English sites」を
# 並べるだけのページで、部活へのリンクが1枚目に無い。こういう校だけ1ホップ追う。
ENTRY_TEXT = ("日本語",)
ENTRY_URL = ("index_jp", "index-jp", "japanese")


def extract_title(html: str) -> str:
    m = TITLE_RE.search(html)
    return re.sub(r"\s+", " ", TAG_RE.sub("", m.group(1))).strip() if m else ""


def find_club_urls(html: str, top_url: str) -> list[tuple[int, str, str]]:
    """部活動ページらしきリンクを、確からしい順に返す。

    @return [(得点, 絶対URL, リンク文字列)]
    """
    top = urllib.parse.urlparse(top_url)
    # トップが /zen/zennichi.html のような個別ファイルのこともあるので、
    # その場合は置かれているディレクトリを基準にする
    base_dir = top.path if top.path.endswith("/") else top.path.rsplit("/", 1)[0] + "/"

    seen: dict[str, tuple[int, str]] = {}
    for href, inner in LINK_RE.findall(html):
        text = re.sub(r"\s+", "", TAG_RE.sub("", inner))
        href = href.split("#")[0].strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue

        absu = urllib.parse.urljoin(top_url, href)
        p = urllib.parse.urlparse(absu)
        if p.scheme not in ("http", "https") or p.netloc != top.netloc:
            continue
        if not p.path.startswith(base_dir) or ARTICLE_RE.search(p.path):
            continue

        rel = p.path[len(base_dir):]
        if not rel or rel.endswith((".pdf", ".jpg", ".png", ".xml")):
            continue

        score = 0
        if any(k in text for k in TEXT_STRONG):
            score += 10
        if any(k in text for k in TEXT_WEAK):
            score += 2
        low = rel.lower()
        if any(k in low for k in URL_HINTS):
            score += 4
        # 「部活動・生徒会」のような一覧ページを、下層の個別ページより上に置く
        if low.endswith(("activities.html", "activities/", "club.html", "clubs.html")):
            score += 3
        if score <= 0:
            continue

        clean = urllib.parse.urlunparse(p._replace(query="", fragment=""))
        if clean not in seen or seen[clean][0] < score:
            seen[clean] = (score, text[:40])

    ranked = [(sc, u, txt) for u, (sc, txt) in seen.items()]
    # 得点が同じならパスが短いほうを優先（下層の個別ページより一覧が上に来る）
    ranked.sort(key=lambda x: (-x[0], len(x[1])))
    return ranked


def find_entry_url(html: str, top_url: str) -> str:
    """入口ページから、本編トップらしきリンクを1つだけ返す。"""
    top = urllib.parse.urlparse(top_url)
    for href, inner in LINK_RE.findall(html):
        text = re.sub(r"\s+", "", TAG_RE.sub("", inner))
        href = href.split("#")[0].strip()
        if not href:
            continue
        absu = urllib.parse.urljoin(top_url, href)
        p = urllib.parse.urlparse(absu)
        if p.netloc != top.netloc or absu.rstrip("/") == top_url.rstrip("/"):
            continue
        low = p.path.lower()
        if any(k in text for k in ENTRY_TEXT) or any(k in low for k in ENTRY_URL):
            return absu
    return ""


# ---------------------------------------------------------------- 取得

def cache_path(url: str) -> Path:
    """トップページのキャッシュ先。

    www.metro.ed.jp/<slug>/ は <slug>.html にする。別ホストや多階層のものは
    URL全体を平坦化した名前にする。
    """
    p = urllib.parse.urlparse(url)
    path = p.path.strip("/")
    if p.netloc == "www.metro.ed.jp" and path and "/" not in path:
        return TOPS_DIR / f"{path}.html"
    flat = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{p.netloc}_{path}").strip("_")
    return TOPS_DIR / f"{flat or p.netloc}.html"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="取得済みHTMLだけで生成（通信しない）")
    ap.add_argument("--force", action="store_true", help="トップページを取り直す")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC,
                    help=f"リクエスト間隔の下限秒（既定 {DEFAULT_DELAY_SEC}）")
    args = ap.parse_args()

    TOPS_DIR.mkdir(parents=True, exist_ok=True)

    # --- 一次ソース ---
    if args.offline:
        if not LIST_XLSX.is_file():
            sys.exit(f"{LIST_XLSX} がありません。--offline を外して実行してください")
        blob = LIST_XLSX.read_bytes()
        print(f"オフライン: {LIST_XLSX.relative_to(ROOT)} を使います")
    else:
        print(f"User-Agent: {USER_AGENT}")
        print(f"一覧を取得: {LIST_URL}")
        status, blob = fetch(LIST_URL)
        if status != 200:
            sys.exit(f"list.xlsx が HTTP {status}")
        LIST_XLSX.write_bytes(blob)   # 出典として現物を残す

    listed = read_school_list(blob)
    zennichi = [r for r in listed if r["course"].lstrip().startswith("全日制")]
    print(f"一覧 {len(listed)}行 → 全日制 {len(zennichi)}校\n")

    # --- マスタと突き合わせ ---
    with MASTER_CSV.open(encoding="utf-8-sig", newline="") as f:
        master = list(csv.DictReader(f))
    by_name = {r["name"]: r for r in master}

    problems: list[dict[str, str]] = []
    targets: list[dict[str, str]] = []

    for r in zennichi:
        short = r["name"].replace("高等学校", "").strip()
        school = by_name.get(short)
        if not school:
            problems.append({"name": r["name"], "url": r["url"],
                             "reason": f"マスタに『{short}』が無い"})
            continue
        # 学校IDは裏取りにだけ使う。食い違っても止めないが、黙って通しもしない
        if r["school_id"] and r["school_id"][1:] != school["school_number"]:
            problems.append({"name": r["name"], "url": r["url"],
                             "reason": f"学校IDが不一致（一覧 {r['school_id']} / "
                                       f"マスタ {school['school_number']}）。校名で照合した"})
        targets.append({**r, "short": short, "school": school})

    dup = [n for n in {t["short"] for t in targets}
           if sum(1 for t in targets if t["short"] == n) > 1]
    if dup:
        problems.append({"name": "/".join(dup), "url": "", "reason": "校名が重複している"})

    # --- トップページ ---
    crawler = Crawler(args.delay)
    fetched = cached = 0

    for t in targets:
        dest = cache_path(t["url"])
        t["cache"] = dest
        if dest.exists() and not args.force:
            cached += 1
            continue
        if args.offline:
            continue
        try:
            status, body = crawler.get(t["url"])
        except Exception as e:
            print(f"  FAIL  {t['short']}: {e}")
            problems.append({"name": t["name"], "url": t["url"], "reason": str(e)})
            continue
        if status != 200:
            print(f"  FAIL  {t['short']}: HTTP {status}")
            problems.append({"name": t["name"], "url": t["url"], "reason": f"HTTP {status}"})
            continue
        dest.write_bytes(body)
        fetched += 1
        print(f"  OK    {t['short']}: {dest.name}")

    print(f"\n取得 {fetched} / キャッシュ {cached}\n")

    # --- 部活ページ発見 ---
    rows: list[dict[str, str]] = []
    for t in targets:
        dest: Path = t["cache"]
        if not dest.exists():
            problems.append({"name": t["name"], "url": t["url"], "reason": "トップページ未取得"})
            continue
        html = dest.read_text(encoding="utf-8", errors="replace")
        page_url = t["url"]
        ranked = find_club_urls(html, page_url)
        via = ""

        # 入口ページだった場合だけ、1ホップ追って探し直す
        if not ranked:
            entry = find_entry_url(html, page_url)
            if entry:
                entry_cache = cache_path(entry)
                try:
                    if entry_cache.exists() and not args.force:
                        body = entry_cache.read_bytes()
                    elif args.offline:
                        raise RuntimeError("入口ページが未取得（--offline のため取得しない）")
                    else:
                        status, body = crawler.get(entry)
                        if status != 200:
                            raise RuntimeError(f"HTTP {status}")
                        entry_cache.write_bytes(body)
                    page_url, via = entry, entry
                    ranked = find_club_urls(body.decode("utf-8", errors="replace"), entry)
                    print(f"  HOP   {t['short']}: {entry}")
                except Exception as e:
                    problems.append({"name": t["name"], "url": entry,
                                     "reason": f"入口ページの追跡に失敗: {e}"})

        best = ranked[0] if ranked else None
        if not best:
            problems.append({"name": t["name"], "url": t["url"],
                             "reason": "部活動ページのリンクが見つからない"})

        rows.append({
            "school_number": t["school"]["school_number"],
            "name": t["short"],
            "official_name": t["name"],
            "course": t["course"],
            "top_url": t["url"],
            "clubs_url": best[1] if best else "",
            "status": "ok" if best else "no_club_page",
            "club_link_text": best[2] if best else "",
            "clubs_url_alt": ranked[1][1] if len(ranked) > 1 else "",
            "via": via,
            "source": SOURCE_LABEL,
        })

    rows.sort(key=lambda r: r["school_number"])

    fields = ["school_number", "name", "official_name", "course", "top_url",
              "clubs_url", "status", "club_link_text", "clubs_url_alt", "via", "source"]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    if problems:
        with PROBLEMS_CSV.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "url", "reason"])
            w.writeheader()
            w.writerows(problems)
    elif PROBLEMS_CSV.exists():
        PROBLEMS_CSV.unlink()

    ok = sum(1 for r in rows if r["status"] == "ok")
    listed_names = {t["short"] for t in targets}
    missing = [r["name"] for r in master
               if "全日制" in (r["course_types"] or "") and r["name"] not in listed_names]

    print(f"{OUT_CSV.relative_to(ROOT)} -> {len(rows)}行")
    print(f"  部活ページ解決  {ok}校")
    print(f"  未解決          {len(rows) - ok}校")
    print(f"  要確認          {len(problems)}件"
          + (f" -> {PROBLEMS_CSV.relative_to(ROOT)}" if problems else ""))
    print(f"  一覧に載っていないマスタ校 {len(missing)}校: {missing}")


if __name__ == "__main__":
    main()
