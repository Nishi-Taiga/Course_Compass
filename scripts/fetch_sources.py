#!/usr/bin/env python3
"""都教委などの一次ソースをダウンロードする（GitHub Actionsランナーで実行）。

実行環境の前提: Claude Code側のプロキシは都庁系に不達のため、
外部ネットワークが開いているActionsランナー上で本スクリプトを回し、
結果を data/fetched/ にコミットして受け渡す。

URLリスト: scripts/fetch_urls.txt（`キー<空白>URL` 形式、#行は無視）
出力: data/fetched/{キー}.{拡張子} と data/fetched/INDEX.md
"""
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "fetched"
UA = ("toritsu-compass-data-fetch/0.1 (Tokyo ODH2026 hackathon; "
      "contact: team WINS)")
DELAY_SEC = 2.0


def guess_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct or url.lower().endswith(".pdf"):
        return ".pdf"
    if "csv" in ct or url.lower().endswith(".csv"):
        return ".csv"
    if "excel" in ct or "spreadsheet" in ct or url.lower().endswith((".xlsx", ".xls")):
        return ".xlsx"
    if "json" in ct:
        return ".json"
    return ".html"


def main() -> int:
    urls_file = BASE / "scripts" / "fetch_urls.txt"
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in urls_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, url = line.split(None, 1)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                ext = guess_ext(url, r.headers.get("Content-Type", ""))
                path = OUT / f"{key}{ext}"
                path.write_bytes(body)
                rows.append((key, url, f"OK {len(body):,}B -> {path.name}"))
        except Exception as e:  # noqa: BLE001 - 記録して続行
            rows.append((key, url, f"FAIL {type(e).__name__}: {e}"))
        time.sleep(DELAY_SEC)

    index = ["# fetch結果", "", "| キー | 結果 | URL |", "|---|---|---|"]
    index += [f"| {k} | {res} | {u} |" for k, u, res in rows]
    (OUT / "INDEX.md").write_text("\n".join(index) + "\n")
    print("\n".join(f"{k}: {res}" for k, u, res in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
