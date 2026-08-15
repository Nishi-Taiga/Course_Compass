#!/usr/bin/env python3
"""取得済みHTMLから部活リストを抽出する（GPT-OSS 20B / Workers AI）。

    python3 scripts/extract_school_clubs.py --dry-run   # 送信内容だけ確認（LLMを呼ばない）
    python3 scripts/extract_school_clubs.py             # 実際に抽出

学校ごとにHTMLの作りがバラバラで、決め打ちのパーサーが書けない。
そのためHTMLを丸ごとLLMに渡して部活名を列挙させる。
GPT-OSS 20B を使うのは 128k コンテキストでHTMLが丸ごと入るため
（Qwen2.5 Coder 32B は入力コスト約10倍なので使わない）。

⚠️ 表記ゆれ（サッカー部 / サッカー / 足球部）はここで正規化しない。
   サイト上の表記そのままを raw_name に保存する。正規化辞書は西が監修し、
   後段で normalized に埋める。ここで潰すと元表記に戻せなくなる。

⚠️ 部活は「有無のリスト」まで。盛んかどうかはMVPで持たない（仕様書§6.2）。

認証情報はソースに書かない（規約）。環境変数から読む:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_school_clubs import slug_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITES_CSV = ROOT / "data" / "seed" / "school_sites.csv"
HTML_DIR = ROOT / "data" / "fetched" / "clubs"
RESOLVED_CSV = HTML_DIR / "_resolved.csv"
OUT_CSV = ROOT / "data" / "seed" / "school_clubs.csv"

MODEL = "@cf/openai/gpt-oss-20b"


def decode_html(body: bytes) -> str:
    """HTMLを文字列にする。文字コードは meta の charset を見てから決める。

    五日市の部活ページだけ Shift_JIS で、utf-8 決め打ちだと全部が文字化けし、
    そのままLLMに渡すと部活名を1つも取れない。
    """
    m = re.search(rb"""charset=["']?([A-Za-z0-9_\-]+)""", body[:2000])
    candidates = [m.group(1).decode("ascii", "ignore")] if m else []
    for enc in candidates + ["utf-8", "cp932", "euc-jp"]:
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")

SYSTEM_PROMPT = """あなたはHTMLから部活動の一覧を抜き出す抽出器です。
次の規則に厳密に従ってください。

1. HTMLに実際に書かれている部活動・同好会だけを挙げる。推測で補わない。
2. 表記はページ上のものをそのまま使う。「部」を足したり削ったりしない。
   例: ページに「サッカー」とあれば「サッカー」、「サッカー部」とあれば「サッカー部」。
3. カテゴリ見出し（運動部・文化部・学芸部など）があれば category に入れる。
   無ければ category は null。
4. 委員会・生徒会・部活動以外の組織は含めない。
5. 出力はJSONのみ。前置きも説明も付けない。

出力形式:
{"clubs":[{"raw_name":"サッカー部","category":"運動部"}]}"""


def strip_noise(html: str) -> str:
    """script/style/コメントだけ落とす。構造は残す（見出しがカテゴリの手がかりになる）。"""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    return re.sub(r"\n{3,}", "\n\n", html)


def call_workers_ai(system: str, user: str) -> str:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account or not token:
        sys.exit(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN が未設定です。\n"
            "ハッカソン用チームの招待が済んでから実行してください。\n"
            "送信内容だけ確認したい場合は --dry-run を付けてください。"
        )

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 2048,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        body = json.load(res)

    if not body.get("success", True):
        sys.exit(f"Workers AI エラー: {body.get('errors')}")
    result = body.get("result", {})
    return result.get("response") if isinstance(result, dict) else str(result)


def parse_clubs(text: str) -> list[dict]:
    """LLMの出力からJSONを取り出す。前後に文が付いていても拾えるようにする。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M)
    start = text.find("{")
    if start < 0:
        raise ValueError(f"JSONが見つかりません: {text[:200]}")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    clubs = obj.get("clubs", [])
    if not isinstance(clubs, list):
        raise ValueError("clubs が配列ではありません")
    return clubs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("schools", nargs="*", help="対象の学校名（省略時は取得済み全校）")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLMを呼ばず、送信するプロンプトの要約だけ表示する")
    args = ap.parse_args()

    with SITES_CSV.open(encoding="utf-8-sig", newline="") as f:
        targets = list(csv.DictReader(f))
    if args.schools:
        targets = [t for t in targets if t["name"] in args.schools]

    # iframe等で実際の取得先が clubs_url と違う学校（広尾・五日市）。
    # 出典はLLMに渡す文面にも入るので、実際に取った方のURLを使う。
    effective: dict[str, str] = {}
    if RESOLVED_CSV.is_file():
        with RESOLVED_CSV.open(encoding="utf-8-sig", newline="") as f:
            effective = {r["name"]: r["effective_url"] for r in csv.DictReader(f)}

    rows: list[dict] = []
    for t in targets:
        html_path = HTML_DIR / f"{t['school_number']}_{slug_of(t)}.html"
        if not html_path.is_file():
            print(f"  skip  {t['name']}: HTML未取得（先に fetch_school_clubs.py）")
            continue

        html = strip_noise(decode_html(html_path.read_bytes()))
        source_url = effective.get(t["name"]) or t["clubs_url"]
        user = f"学校名: {t['name']}\n出典: {source_url}\n\n--- HTML ---\n{html}"

        if args.dry_run:
            print(f"  {t['name']}: HTML {len(html):,}字 / 推定 {len(html)//3:,} トークン "
                  f"（{MODEL} の128k以内）")
            continue

        print(f"  {t['name']}: 抽出中...")
        clubs = parse_clubs(call_workers_ai(SYSTEM_PROMPT, user))
        for c in clubs:
            rows.append({
                "school_number": t["school_number"],
                "school_name": t["name"],
                "raw_name": c.get("raw_name", "").strip(),
                "category": (c.get("category") or "").strip(),
                "source_url": source_url,
            })
        print(f"    {len(clubs)}件")

    if args.dry_run:
        print("\n--dry-run のためLLMは呼んでいません。")
        return

    if rows:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f, fieldnames=["school_number", "school_name", "raw_name", "category", "source_url"]
            )
            w.writeheader()
            w.writerows(rows)
        print(f"\n{len(rows)}件 -> {OUT_CSV}")
        print("※ 受け入れ条件の8割判定は、学校サイトを見て目視で答え合わせすること。")


if __name__ == "__main__":
    main()
