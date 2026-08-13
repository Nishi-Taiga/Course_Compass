#!/usr/bin/env python3
"""各校公式サイトから部活動ページのHTMLを取得して保存する。

    python3 scripts/fetch_school_clubs.py            # data/seed/school_sites.csv の全校
    python3 scripts/fetch_school_clubs.py 日比谷 神津  # 学校名を指定
    python3 scripts/fetch_school_clubs.py --force     # 取得済みも取り直す

収集元は各校公式サイトのみ（民間まとめサイトは規約・著作権の観点で不採用・仕様書§6.2）。

サーバに負荷をかけないための決まりごと:
  - robots.txt を起動時に1回だけ読み、Disallow と Crawl-delay に従う
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
    print("robots.txt を確認します...")
    disallow, robots_delay = load_robots(BASE)
    delay = max(args.delay, robots_delay)
    print(f"  Disallow: {disallow or '（なし）'}")
    print(f"  リクエスト間隔: {delay:.1f}秒")
    print()

    failures: list[dict[str, str]] = []
    fetched = skipped = 0
    first = True

    for t in targets:
        name, slug = t["name"], t["slug"]
        path = f"/{slug}/{t['clubs_path']}"
        url = urllib.parse.urljoin(BASE, path.lstrip("/"))
        dest = OUT_DIR / f"{t['school_number']}_{slug}.html"

        if dest.exists() and not args.force:
            print(f"  skip  {name}（取得済み: {dest.name}）")
            skipped += 1
            continue

        rule = is_blocked(path, disallow)
        if rule:
            print(f"  BLOCK {name}: robots.txt の Disallow: {rule} に該当。取得しません")
            failures.append({"name": name, "url": url, "reason": f"robots.txt Disallow: {rule}"})
            continue

        # 2回目以降は必ず間隔をあけてから叩く
        if not first:
            time.sleep(delay)
        first = False

        try:
            status, body = fetch(url)
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
