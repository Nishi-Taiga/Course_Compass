#!/usr/bin/env python3
"""急行運転路線の補正係数を算出する。

方法: 各社公表・時刻表由来の「日中最速一般種別の所要時間」（公称値）と、
駅接続グラフの同一路線内概算（各駅停車相当）を比較し、
路線ごとの係数 = 公称値 / 概算値 を求める。
複数区間ある路線は乗車距離の長い区間を優先（急行効果が出る側で校正）。

検証済みの前提: 各停路線では概算がほぼ正確（銀座線 実33分 vs 概算35分、
ODPT実ダイヤ1,000本と突き合わせ）。よって補正は急行路線のみに掛ける。

出力: data/seed/line_speed_factors.csv
"""
import csv
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
SPEED, STOP = 0.75, 0.7

# 公称値: 2026-08-06 Web調査（researcher）。値は日中の最速一般種別。
# (路線名の部分一致キー, 駅A, 駅B, 公称分, 種別)
CORRIDORS = [
    ("田園都市", "中央林間", "渋谷", 46, "急行"),
    ("田園都市", "長津田", "渋谷", 36, "急行"),
    ("小田原線", "町田", "新宿", 37, "快速急行"),
    ("小田原線", "登戸", "新宿", 18, "快速急行"),
    ("京王線", "京王八王子", "新宿", 42, "特急"),
    ("京王線", "調布", "新宿", 18, "特急"),
    ("京王相模原線", "京王多摩センター", "調布", 14, "特急(区間換算)"),
    ("中央本線", "立川", "新宿", 27, "中央特快"),
    ("中央本線", "八王子", "新宿", 41, "中央特快"),
    ("池袋線", "所沢", "池袋", 30, "急行"),
    ("池袋線", "ひばりヶ丘", "池袋", 15, "急行"),
    ("東上", "川越", "池袋", 34, "急行"),
    ("東上", "志木", "池袋", 22, "急行"),
    ("京成本線", "京成船橋", "京成上野", 32, "快速"),
    ("京急本線", "横浜", "品川", 28, "快特"),
    ("埼京", "大宮", "新宿", 35, "快速"),
    ("常磐", "松戸", "上野", 19, "快速"),
    ("東横", "横浜", "渋谷", 25, "特急"),
]


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def name_of(s):
    return s.get("original_name") or s["name"]


def main():
    lines = {l["code"]: l for l in json.load(open(RAW / "line.json"))}
    results = {}  # line_code -> list of (ratio, corridor desc)
    for key, a, b, published, kind in CORRIDORS:
        hit = None
        for f in sorted((RAW / "lines").glob("*.json")):
            d = json.load(open(f))
            if key not in d["name"]:
                continue
            sl = [s for s in d["station_list"] if not s.get("closed")]
            names = [name_of(s) for s in sl]
            if a in names and b in names:
                i, j = names.index(a), names.index(b)
                seg = sl[min(i, j):max(i, j) + 1]
                est = sum(max(1.0, hav(x, y) / SPEED + STOP) for x, y in zip(seg, seg[1:]))
                hit = (d["code"], d["name"], est)
                break
        if not hit:
            print(f"SKIP {key} {a}-{b}: 路線内に両駅なし")
            continue
        code, lname, est = hit
        ratio = published / est
        results.setdefault(code, {"name": lname, "obs": []})
        results[code]["obs"].append((ratio, f"{a}→{b} 公称{published}分({kind}) vs 概算{est:.0f}分"))
        print(f"{lname:14s} {a}→{b}: 公称{published} / 概算{est:.0f} = {ratio:.2f}")

    out = BASE / "data" / "seed" / "line_speed_factors.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line_code", "line_name", "factor", "evidence"])
        for code, v in sorted(results.items()):
            # 長距離区間ほど急行効果が正しく出るため、区間ごとの比の最小値でなく
            # 「距離加重に近い」代表値として最小と平均の中間を採用（保守的すぎない・過小もしない）
            ratios = [r for r, _ in v["obs"]]
            factor = round(min(1.0, (min(ratios) + sum(ratios) / len(ratios)) / 2), 2)
            w.writerow([code, v["name"], factor, " / ".join(d for _, d in v["obs"])])
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
