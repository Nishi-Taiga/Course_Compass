#!/usr/bin/env python3
"""ODPT（公共交通オープンデータセンター）から校正用データを取得する。

用途: 駅接続グラフ（build_commute_graph.py）の急行補正。
      距離ベース概算は各駅停車相当のため、急行運転の多い路線で
      実ダイヤの最速所要時間と突き合わせて路線別補正係数を作る。

実行環境: GitHub Actions ランナー（ODPT_TOKEN を Secrets から注入）。
トークンをログ・コミットに残さないこと。URLはエンドポイント名のみ表示する。

出力: data/odpt/*.json.gz と data/odpt/INDEX.md
"""
import gzip
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "odpt"
API = "https://api.odpt.org/api/v4"
TOKEN = os.environ.get("ODPT_TOKEN", "")

# 急行運転が多く、概算の過大評価が疑われる路線を校正対象にする
CAL_RAILWAYS = [
    "odpt.Railway:Tokyu.DenEnToshi",     # 田園都市線（町田圏の検証で×1.8過大）
    "odpt.Railway:Odakyu.Odawara",       # 小田急小田原線
    "odpt.Railway:Keio.Keio",            # 京王線
    "odpt.Railway:JR-East.ChuoRapid",    # 中央線快速
    "odpt.Railway:Seibu.Ikebukuro",      # 西武池袋線
    "odpt.Railway:Tobu.Tojo",            # 東武東上線
    "odpt.Railway:Keisei.Main",          # 京成本線
]


def fetch(endpoint: str, params: dict) -> bytes:
    q = dict(params)
    q["acl:consumerKey"] = TOKEN
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "course-compass-calibration/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def save(name: str, data: bytes) -> str:
    path = OUT / f"{name}.json.gz"
    with gzip.open(path, "wb") as f:
        f.write(data)
    return f"{len(data):,}B -> {path.name}"


def main() -> int:
    if not TOKEN:
        print("ODPT_TOKEN が未設定です（GitHub Secrets に登録してください）")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []

    # 1) 路線マスタ（全件・小さい）: 路線ID→駅順の対応に使う
    for ep, name, params in [
        ("odpt:Railway", "railways", {}),
        ("odpt:RailwayFare", "_skip", None),  # 使わない（記録用の例示）
    ]:
        if params is None:
            continue
        try:
            rows.append((name, save(name, fetch(ep, params))))
        except Exception as e:  # noqa: BLE001
            rows.append((name, f"FAIL {type(e).__name__}"))
        time.sleep(1)

    # 2) 校正対象路線の駅一覧と平日列車時刻表
    for rw in CAL_RAILWAYS:
        key = rw.split(":")[1].replace(".", "_")
        for ep, suffix, params in [
            ("odpt:Station", "stations", {"odpt:railway": rw}),
            ("odpt:TrainTimetable", "timetable",
             {"odpt:railway": rw, "odpt:calendar": "odpt.Calendar:Weekday"}),
        ]:
            try:
                rows.append((f"{key}_{suffix}", save(f"{key}_{suffix}", fetch(ep, params))))
            except Exception as e:  # noqa: BLE001
                rows.append((f"{key}_{suffix}", f"FAIL {type(e).__name__}: {e}"))
            time.sleep(1.5)

    index = ["# ODPT取得結果（校正用・平日ダイヤ）", "",
             "出典: 公共交通オープンデータセンター（ODPT）。各事業者の公共交通データ。", "",
             "| 名前 | 結果 |", "|---|---|"]
    index += [f"| {n} | {res} |" for n, res in rows]
    (OUT / "INDEX.md").write_text("\n".join(index) + "\n")
    print("\n".join(f"{n}: {res}" for n, res in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
