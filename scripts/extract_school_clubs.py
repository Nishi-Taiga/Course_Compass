#!/usr/bin/env python3
"""取得済みHTMLから部活リストを抽出する。

    python3 scripts/extract_school_clubs.py                # 構造で抽出（既定・LLM不要）
    python3 scripts/extract_school_clubs.py --engine llm   # Workers AI で抽出
    python3 scripts/extract_school_clubs.py --dry-run      # LLMに送る内容だけ確認

抽出の仕方は2つある。出力するCSVは同じなので、あとから差し替えて比べられる。

  rules（既定） … HTMLの構造から抜く。scripts/parse_clubs.py。Cloudflare不要
  llm           … HTMLを丸ごと GPT-OSS 20B に渡して列挙させる。128kコンテキスト
                  （Qwen2.5 Coder 32B は入力コスト約10倍なので使わない）

当初は「学校ごとにHTMLがバラバラで決め打ちパーサーは書けない」と考えて llm だけを
用意したが、167校ぶん取得して数え直すと大半が共通CMSの決まった形だった。
正解リスト（3校80部）に対して rules は 80/80 を再現する。受け入れ条件は8割。

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
from parse_clubs import (  # noqa: E402
    decode_html,
    strip_noise,
    parse_clubs as parse_clubs_from_html,   # 構造で抜く方。LLM出力を読む parse_clubs と別物
)

ROOT = Path(__file__).resolve().parent.parent
SITES_CSV = ROOT / "data" / "seed" / "school_sites.csv"
HTML_DIR = ROOT / "data" / "fetched" / "clubs"
RESOLVED_CSV = HTML_DIR / "_resolved.csv"
OUT_CSV = ROOT / "data" / "seed" / "school_clubs.csv"

MODEL = "@cf/openai/gpt-oss-20b"



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
    ap.add_argument("--engine", choices=["rules", "llm"], default="rules",
                    help="rules=HTMLの構造から抜く（既定・Cloudflare不要） / llm=Workers AI")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLMを呼ばず、送信するプロンプトの要約だけ表示する（--engine llm 用）")
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
    thin: list[str] = []          # 取れた数が少ない学校。目視に回す
    missing: list[str] = []

    for t in targets:
        html_path = HTML_DIR / f"{t['school_number']}_{slug_of(t)}.html"
        if not html_path.is_file():
            print(f"  skip  {t['name']}: HTML未取得（先に fetch_school_clubs.py）")
            missing.append(t["name"])
            continue

        raw_html = decode_html(html_path.read_bytes())
        source_url = effective.get(t["name"]) or t["clubs_url"]

        if args.engine == "rules":
            clubs, how = parse_clubs_from_html(raw_html)
        else:
            html = strip_noise(raw_html)
            user = f"学校名: {t['name']}\n出典: {source_url}\n\n--- HTML ---\n{html}"
            if args.dry_run:
                print(f"  {t['name']}: HTML {len(html):,}字 / 推定 {len(html)//3:,} トークン "
                      f"（{MODEL} の128k以内）")
                continue
            print(f"  {t['name']}: 抽出中...")
            clubs, how = parse_clubs(call_workers_ai(SYSTEM_PROMPT, user)), MODEL

        for c in clubs:
            name = (c.get("raw_name") or "").strip()
            if not name:
                continue
            rows.append({
                "school_number": t["school_number"],
                "school_name": t["name"],
                "raw_name": name,
                "category": (c.get("category") or "").strip(),
                "source_url": source_url,
                "engine": how,
            })

        # 都立で部活が5つ未満というのは考えにくい。取りこぼしを疑って印を付ける
        if len(clubs) < 5:
            thin.append(f"{t['name']}({len(clubs)})")
        print(f"  {t['name']:12} {len(clubs):3}件  [{how}]")

    if args.dry_run:
        print("\n--dry-run のためLLMは呼んでいません。")
        return

    if rows:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "school_number", "school_name", "raw_name", "category", "source_url", "engine"
            ])
            w.writeheader()
            w.writerows(rows)

        schools = len({r["school_number"] for r in rows})
        print(f"\n{len(rows)}件 / {schools}校 -> {OUT_CSV}")
        if thin:
            print(f"⚠️ 5件未満の学校 {len(thin)}校（目視で確認）: {'、'.join(thin)}")
        if missing:
            print(f"⚠️ HTML未取得 {len(missing)}校: {'、'.join(missing)}")
        print("※ 8割判定の答え合わせは data/seed/school_clubs_expected.md（3校80部）で行う。")


if __name__ == "__main__":
    main()
