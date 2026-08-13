#!/usr/bin/env python3
"""各校公式サイトから部活動ページのHTMLを取得して保存する。

    python3 scripts/fetch_school_clubs.py            # data/seed/school_sites.csv の全校
    python3 scripts/fetch_school_clubs.py 日比谷 神津  # 学校名を指定
    python3 scripts/fetch_school_clubs.py --force     # 取得済みも取り直す

収集元は各校公式サイトのみ（民間まとめサイトは規約・著作権の観点で不採用・仕様書§6.2）。
取得先URLは data/seed/school_sites.csv の clubs_url 列。この台帳は
scripts/build_school_sites.py が都立学校ポータルの公式一覧から作る。

サーバに負荷をかけないための決まりごと:
  - robots.txt をホストごとに1回だけ読み、Disallow と Crawl-delay に従う
  - リクエスト間隔は既定 3秒（要件は2秒以上。余裕を持たせている）
  - Crawl-delay が3秒より長ければそちらに従う
  - User-Agent で正直に名乗る（連絡先としてリポジトリURLを入れる）
  - 取得済みはスキップする。何度流しても同じ場所を叩き直さない

Step6（190校バッチ）でも同じスクリプトを使う。途中で止まっても
再実行すれば続きから進む（取得済みスキップがその仕組み）。
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES_CSV = ROOT / "data" / "seed" / "school_sites.csv"
OUT_DIR = ROOT / "data" / "fetched" / "clubs"
FAILURES_CSV = OUT_DIR / "_failures.csv"

BASE = "https://www.metro.ed.jp/"

# 連絡先を名乗る。サイト管理者がログを見て問い合わせられるようにするため。
# HTTPヘッダは latin-1 しか通らないので ASCII のみで書く（日本語を入れると送信前に落ちる）。
USER_AGENT = (
    "CourseCompass-Bot/0.1 "
    "(+https://github.com/Nishi-Taiga/Course_Compass; "
    "research use for Tokyo open data hackathon 2026)"
)

DEFAULT_DELAY_SEC = 3.0   # 要件は2秒以上。余裕を持たせる
TIMEOUT_SEC = 30


def fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        return res.status, res.read()


def load_robots(base: str) -> tuple[list[str], float]:
    """robots.txt を1回だけ読む。(禁止パス一覧, 待つべき秒数) を返す。

    読めなかった場合は「制限なし」と解釈する（慣例）。ただし、
    その旨は必ず表示して、黙って素通りしないようにする。
    """
    url = urllib.parse.urljoin(base, "/robots.txt")
    try:
        status, body = fetch(url)
    except Exception as e:
        print(f"  robots.txt を読めませんでした（{e}）。制限なしと解釈します。")
        return [], DEFAULT_DELAY_SEC

    if status != 200:
        print(f"  robots.txt が {status}。制限なしと解釈します。")
        return [], DEFAULT_DELAY_SEC

    disallow: list[str] = []
    delay = DEFAULT_DELAY_SEC
    applies = False  # 直前の User-agent 行が自分に当てはまるか

    for raw in body.decode("utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()

        if key == "user-agent":
            # 「*」と、自分の名前を名指ししている節だけを見る
            applies = value == "*" or value.lower() in USER_AGENT.lower()
        elif not applies:
            continue
        elif key == "disallow" and value:
            disallow.append(value)
        elif key == "crawl-delay":
            try:
                # 相手の指定が既定より厳しければ、そちらに従う
                delay = max(delay, float(value))
            except ValueError:
                pass

    return disallow, delay


def is_blocked(path: str, disallow: list[str]) -> str | None:
    for rule in disallow:
        if rule == "/" or path.startswith(rule):
            return rule
    return None


class Crawler:
    """ホストごとに robots.txt を1回だけ読み、間隔をあけて取得する。

    5校（八潮・国際・六郷工科・広尾・五日市）は www.metro.ed.jp ではなく
    自前のホストにサイトを置いている。robots.txt はホストごとに別物なので、
    まとめて1回読むわけにはいかない。間隔もホストごとに数える。
    """

    def __init__(self, min_delay: float = DEFAULT_DELAY_SEC):
        self.min_delay = min_delay
        self.rules: dict[str, tuple[list[str], float]] = {}
        self.last: dict[str, float] = {}

    def rules_for(self, netloc: str) -> tuple[list[str], float]:
        if netloc not in self.rules:
            print(f"  robots.txt を確認します: {netloc}")
            disallow, delay = load_robots(f"https://{netloc}/")
            delay = max(delay, self.min_delay)
            print(f"    Disallow: {disallow or '（なし）'} / 間隔 {delay:.1f}秒")
            self.rules[netloc] = (disallow, delay)
        return self.rules[netloc]

    def get(self, url: str) -> tuple[int, bytes]:
        p = urllib.parse.urlparse(url)
        disallow, delay = self.rules_for(p.netloc)
        rule = is_blocked(p.path or "/", disallow)
        if rule:
            raise PermissionError(f"robots.txt Disallow: {rule}")

        wait = delay - (time.monotonic() - self.last.get(p.netloc, -1e9))
        if wait > 0:
            time.sleep(wait)
        self.last[p.netloc] = time.monotonic()
        return fetch(url)


def slug_of(row: dict[str, str]) -> str:
    """保存ファイル名に使う短い識別子。top_url から作る。

    www.metro.ed.jp/hibiya-h/ → hibiya-h、別ホストなら先頭ラベル（yashio-h など）。
    """
    p = urllib.parse.urlparse(row.get("top_url") or "")
    path = p.path.strip("/").split("/")[0]
    if p.netloc == "www.metro.ed.jp" and path:
        return path
    return p.netloc.split(".")[0] or row["school_number"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("schools", nargs="*", help="対象の学校名（省略時は全校）")
    ap.add_argument("--force", action="store_true", help="取得済みも取り直す")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC,
                    help=f"リクエスト間隔の下限秒（既定 {DEFAULT_DELAY_SEC}）")
    args = ap.parse_args()

    if not SITES_CSV.is_file():
        sys.exit(f"{SITES_CSV} がありません")

    with SITES_CSV.open(encoding="utf-8-sig", newline="") as f:
        targets = list(csv.DictReader(f))
    if args.schools:
        targets = [t for t in targets if t["name"] in args.schools]
        if not targets:
            sys.exit(f"該当する学校がありません: {args.schools}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"User-Agent: {USER_AGENT}")
    crawler = Crawler(args.delay)

    failures: list[dict[str, str]] = []
    fetched = skipped = 0

    for t in targets:
        name = t["name"]
        url = t.get("clubs_url", "")
        dest = OUT_DIR / f"{t['school_number']}_{slug_of(t)}.html"

        if not url:
            print(f"  SKIP  {name}: 部活動ページのURLが未解決（status={t.get('status')}）")
            failures.append({"name": name, "url": t.get("top_url", ""),
                             "reason": "clubs_url が空。build_school_sites.py の出力を確認"})
            continue

        if dest.exists() and not args.force:
            print(f"  skip  {name}（取得済み: {dest.name}）")
            skipped += 1
            continue

        try:
            status, body = crawler.get(url)
        except PermissionError as e:
            print(f"  BLOCK {name}: {e}")
            failures.append({"name": name, "url": url, "reason": str(e)})
            continue
        except urllib.error.HTTPError as e:
            print(f"  FAIL  {name}: HTTP {e.code}")
            failures.append({"name": name, "url": url, "reason": f"HTTP {e.code}"})
            continue
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failures.append({"name": name, "url": url, "reason": str(e)})
            continue

        if status != 200:
            print(f"  FAIL  {name}: HTTP {status}")
            failures.append({"name": name, "url": url, "reason": f"HTTP {status}"})
            continue

        dest.write_bytes(body)
        print(f"  OK    {name}: {len(body):,} bytes -> {dest.name}")
        fetched += 1

    # 失敗校は理由付きで残す（安田の目視検証に回すため）
    if failures:
        with FAILURES_CSV.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "url", "reason"])
            w.writeheader()
            w.writerows(failures)
        print(f"\n失敗 {len(failures)}件 -> {FAILURES_CSV}")
    elif FAILURES_CSV.exists():
        FAILURES_CSV.unlink()

    print(f"\n取得 {fetched} / スキップ {skipped} / 失敗 {len(failures)}（対象 {len(targets)}校）")


if __name__ == "__main__":
    main()
