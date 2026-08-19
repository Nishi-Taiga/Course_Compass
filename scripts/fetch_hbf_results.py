#!/usr/bin/env python3
"""東京都高等学校野球連盟の試合結果を取得する。

    python3 scripts/fetch_hbf_results.py            # 直近2年度ぶん
    python3 scripts/fetch_hbf_results.py --years 3

高体連（tokyo-kotairen）には野球が入っていない。硬式野球は高野連の管轄で、
連盟が別だから。都立の部活動データでは吹奏楽に次ぐ規模なのに実績が
1件も無い状態だったので、こちらから取る。

## 取り方

大会ごとの一覧ページ（春季・選手権・秋季）に、日付ごとの試合結果ページへの
リンクが並んでいる。優勝・準優勝しか書いていないので一覧ページだけでは
都立の実績にならない（優勝校はほぼ私立）。**日付ページまで降りて
1試合ずつ拾い、各校がどこまで勝ち上がったかを出す**。

⚠️ 試合結果ページには**出場選手の氏名が載っている**（投手・捕手・本塁打など）。
   parse_hbf_results.py が学校名・ラウンド・スコアだけを取り出し、氏名は
   一切持たない。取得したHTMLはリポジトリに含めない（.gitignore）。

⚠️ 日付ページのURLは base64 風のトークンで、中に有効期限（exp）が入っている。
   期限切れで404になることがあるので、一覧ページを取り直せば新しい
   リンクが手に入る。取得済みはスキップするので、流し直しは安い。

出力: data/fetched/hbf/*.html ＋ index.csv（大会名・日付・URL）
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fetched" / "hbf"
INDEX_CSV = OUT / "index.csv"

BASE = "https://www.tokyo-hbf.com"
TOURNAMENTS = [
    ("春季", f"{BASE}/pastgame_spring.html"),
    ("選手権", f"{BASE}/pastgame_summer.html"),
    ("秋季", f"{BASE}/pastgame_autumn.html"),
]

UA = ("ShinroCompass/0.1 (+https://github.com/Nishi-Taiga/Course_Compass; "
      "research use for Tokyo open data hackathon 2026)")
DELAY = 3.0


def get(url: str) -> bytes:
    """curl で取る。

    このサイトは Python の urllib だと証明書の検証に失敗する
    （中間証明書が手元の信頼ストアに無い）。curl は自前のCAを持つので通る。
    build_school_coords.py も同じ理由で curl を使っている。
    """
    r = subprocess.run(
        ["curl", "-sS", "-m", "40", "-A", UA, url],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200])
    return r.stdout


# 「第108回全国高等学校野球選手権大会」「令和7年度 秋季東京都高等学校野球大会」など
TITLE_RE = re.compile(r"<h[23][^>]*>(?P<t>[^<]{6,60})</h[23]>")
DAY_RE = re.compile(r'<a[^>]*href="(?P<u>https://www\.tokyo-hbf\.com/pastgame/[^"]+)"[^>]*>'
                    r'(?P<d>[^<]{3,20})</a>')


def parse_index(html: str) -> list[dict]:
    """一覧ページから（大会名, 日付, URL）を拾う。

    見出しと日付リンクを文書の順に走査し、直前の見出しをその日の大会名にする。
    見出しを別に集めて後で対応づけると、大会が入れ違う。
    """
    out = []
    title = ""
    token = re.compile(TITLE_RE.pattern + "|" + DAY_RE.pattern)
    for m in token.finditer(html):
        if m.group("t"):
            t = re.sub(r"\s+", " ", m.group("t")).strip()
            if t:
                title = t
            continue
        out.append({"meet": title, "day": m.group("d").strip(), "url": m.group("u")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=2,
                    help="各大会ページの上から何大会ぶんを取るか（既定2）")
    ap.add_argument("--force", action="store_true", help="取得済みも取り直す")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"User-Agent: {UA}")

    entries: list[dict] = []
    for label, url in TOURNAMENTS:
        print(f"\n=== {label}: {url}")
        try:
            html = get(url).decode("utf-8", "replace")
        except Exception as e:
            print(f"  取得できません: {e}")
            continue
        days = parse_index(html)

        # 大会名ごとにまとめ、新しいものから args.years 大会ぶんだけ残す
        meets: list[str] = []
        for d in days:
            if d["meet"] and d["meet"] not in meets:
                meets.append(d["meet"])
        keep = set(meets[: args.years * 2])      # 東・西で2ブロックあるため2倍
        picked = [d for d in days if d["meet"] in keep]
        print(f"  大会 {len(meets)}件中 {len(keep)}件 / 日付ページ {len(picked)}件")
        for d in picked:
            d["tournament"] = label
        entries.extend(picked)

    fetched = skipped = failed = 0
    for i, e in enumerate(entries, 1):
        # URLのトークンは長いので、通し番号でファイル名を作る
        name = re.sub(r"[^0-9A-Za-z]+", "_", f"{e['tournament']}_{e['meet']}_{e['day']}")[:90]
        dest = OUT / f"{name}.html"
        e["file"] = dest.name

        if dest.exists() and not args.force:
            skipped += 1
            continue
        time.sleep(DELAY)
        try:
            dest.write_bytes(get(e["url"]))
            fetched += 1
        except Exception as ex:
            print(f"  FAIL {e['meet']} {e['day']}: {ex}")
            failed += 1
        if i % 20 == 0:
            print(f"  {i}/{len(entries)}", flush=True)

    with INDEX_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tournament", "meet", "day", "file", "url"])
        w.writeheader()
        w.writerows(entries)

    print(f"\n取得 {fetched} / スキップ {skipped} / 失敗 {failed}（対象 {len(entries)}）")
    print(f"索引 -> {INDEX_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
