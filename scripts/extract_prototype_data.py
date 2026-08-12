#!/usr/bin/env python3
"""prototype/index.html に埋め込まれた通学時間データを CSV に取り出す。

    python3 scripts/extract_prototype_data.py

プロトタイプの `const D = {...}` には、build_commute_graph.py で計算して
急行補正までかけ終わった結果が入っている（647駅 × 49区市）。
build_commute_graph.py 自体は検証用でCSVを書かないため、
D1に入れるにはここから取り出すのが唯一の経路。

あわせて、判定モデル（1020点の差分方式）が使う学校側の値も取り出す。
目安点 target_score は西が8/14に実値を入れるまでの仮値（公開データの層別）。

出力:
  data/seed/stations.csv       647駅（駅名・緯度経度）
  data/seed/ward_stations.csv   49区市 → 代表駅
  data/seed/commute_times.csv  647 × 49 = 31,703行（出発駅 → 区市の所要分）
  data/seed/school_scores.csv  172校（目安点・選抜区分・注意書き・層）

通学時間が「駅→区市」粒度なのは、プロトタイプが学校を所在区市で位置づけて
いるため。学校ごとの最寄駅は持っていないので、この粒度が上限になる。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTOTYPE = ROOT / "prototype" / "index.html"
SEED = ROOT / "data" / "seed"

MARKER = "const D = "


def load_prototype_data() -> dict:
    if not PROTOTYPE.is_file():
        sys.exit(f"{PROTOTYPE} が見つかりません")
    html = PROTOTYPE.read_text(encoding="utf-8")
    try:
        start = html.index(MARKER) + len(MARKER)
    except ValueError:
        sys.exit(f"prototype に `{MARKER}` が見つかりません（構造が変わった可能性）")
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    return data


def main() -> None:
    d = load_prototype_data()

    stations = d["stations"]      # 647駅（commute の値の並び順とは無関係）
    wards = d["wards"]            # 49区市（commute の各配列の並び順と一致）
    commute = d["commute"]        # 駅名 -> 区市ごとの所要分（wards と同じ並び）
    rep = d["rep"]                # 区市 -> 代表駅
    xy = d["xy"]                  # 駅名 -> [lat, lon]

    # --- 前提が崩れていないか確認してから書く ---
    missing_xy = [s for s in stations if s not in xy]
    if missing_xy:
        sys.exit(f"座標が無い駅: {missing_xy[:10]}")

    missing_commute = [s for s in stations if s not in commute]
    if missing_commute:
        sys.exit(f"通学時間が無い駅: {missing_commute[:10]}")

    bad_len = [s for s in stations if len(commute[s]) != len(wards)]
    if bad_len:
        sys.exit(f"区市数({len(wards)})と長さが合わない駅: {bad_len[:10]}")

    missing_rep = [w for w in wards if w not in rep]
    if missing_rep:
        sys.exit(f"代表駅が無い区市: {missing_rep}")

    SEED.mkdir(parents=True, exist_ok=True)

    # --- stations.csv ---
    with (SEED / "stations.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station_name", "lat", "lon"])
        for s in stations:
            lat, lon = xy[s]
            w.writerow([s, lat, lon])

    # --- ward_stations.csv ---
    with (SEED / "ward_stations.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ward", "rep_station"])
        for ward in wards:
            w.writerow([ward, rep[ward]])

    # --- commute_times.csv ---
    rows = 0
    with (SEED / "commute_times.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_station", "to_ward", "minutes"])
        for s in stations:
            for ward, minutes in zip(wards, commute[s]):
                w.writerow([s, ward, minutes])
                rows += 1

    # --- school_scores.csv（判定モデル用） ---
    # t   = 目安点（1020点満点）。西が8/14に実値を入れるまでの仮値
    # st  = 選抜区分 std / jiko / keisha / fukasawa / ratio64 / no_exam
    # sn  = 区分の注意書き（表示するだけ。計算式は分岐しない）
    # ly  = 目安点の層ラベル
    # x   = 1 なら高校からの募集停止（中高一貫）
    schools = d["schools"]
    with (SEED / "school_scores.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "target_score", "selection_type", "selection_note",
                    "score_layer", "no_hs_admission"])
        for s in schools:
            w.writerow([
                s["n"],
                "" if s.get("t") is None else s["t"],
                s.get("st", ""),
                s.get("sn", ""),
                s.get("ly", ""),
                1 if s.get("x") else 0,
            ])

    with_t = sum(1 for s in schools if s.get("t") is not None)
    no_exam = sum(1 for s in schools if s.get("st") == "no_exam")

    print(f"stations.csv      : {len(stations)} 行")
    print(f"ward_stations.csv : {len(wards)} 行")
    print(f"commute_times.csv : {rows} 行")
    print(f"school_scores.csv : {len(schools)} 行"
          f"（目安点あり {with_t} / 学力検査なし {no_exam}）")


if __name__ == "__main__":
    main()
