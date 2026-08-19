#!/usr/bin/env python3
"""高専の通学時間を計算して school_commute_times.csv に足す。

    python3 scripts/fetch_station_db.py       # 先に駅データベースを取得
    python3 scripts/build_kosen_commute.py

## なぜ追加分だけ計算するのか

build_school_commute.py を流し直せば高専も含めて作れるが、既存180校の
11万行がまるごと書き直しになる。上流の駅データベースが更新されていれば
既存校の所要時間も変わり、**高専を足したはずの差分に180校ぶんの変化が
紛れ込む**。レビューで何が変わったのか分からなくなるので、
追加する2校ぶんだけを同じ計算で出し、末尾に足す。

計算そのものは build_school_commute.py の関数をそのまま使う。
式を書き写すと、片方だけ直したときに静かにずれる。
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_school_commute import (  # noqa: E402
    AREA_PREF,
    MAX_MIN,
    dijkstra,
    load_graph,
)

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
EXTRA = SEED / "extra_schools.csv"
OUT = SEED / "school_commute_times.csv"


def main() -> None:
    if not EXTRA.is_file():
        sys.exit(f"{EXTRA} がありません。先に build_kosen.py を実行してください")

    extra = list(csv.DictReader(EXTRA.open(encoding="utf-8-sig")))
    # access 列は「駅:徒歩分|駅:徒歩分」。近い順に並んでいる
    access = {
        r["school_number"]: [
            (s.split(":")[0], int(s.split(":")[1])) for s in r["access"].split("|") if ":" in s
        ]
        for r in extra
    }
    print(f"追加する学校 {len(extra)}校")
    for r in extra:
        print(f"  {r['name']}: " + " / ".join(f"{s}駅 徒歩{m}分" for s, m in access[r['school_number']]))

    t0 = time.time()
    stations, adj, by_station = load_graph()

    # 同名駅の扱いは build_school_commute.main() と揃える（東京を優先）
    name2code = {}
    order = {13: 0, 14: 1, 11: 2, 12: 3}
    for code in sorted(by_station, key=lambda c: order.get(
            stations.get(c, {}).get("prefecture"), 9)):
        s = stations.get(code)
        if s and s.get("prefecture") in AREA_PREF:
            name2code.setdefault(s["name"], code)
            name2code.setdefault(s.get("original_name") or s["name"], code)

    unresolved = {st for opts in access.values() for st, _ in opts if st not in name2code}
    if unresolved:
        print(f"⚠️ 駅名を解決できません: {sorted(unresolved)}")
        print("   駅データベースの表記に合わせて extra_schools.csv の access を直してください")
        sys.exit(1)

    origins = sorted({c for c in by_station
                      if stations.get(c, {}).get("prefecture") == 13})
    print(f"グラフ {len(by_station)}駅 / 出発地(都内) {len(origins)}駅 / {time.time()-t0:.1f}s")

    rows = []
    for i, o in enumerate(origins, 1):
        best = dijkstra(o, adj, by_station)
        oname = stations[o]["name"]
        for sn, opts in access.items():
            cand = None
            for st, walk in opts:
                rail = best.get(name2code[st])
                if rail is None:
                    continue
                total = rail + walk
                if cand is None or total < cand[0]:
                    cand = (total, st)
            if cand and cand[0] <= MAX_MIN:
                rows.append({
                    "from_station": oname,
                    "school_number": sn,
                    "minutes": int(round(cand[0])),
                    "via_station": cand[1],
                    "access_mode": "walk",
                })
        if i % 200 == 0:
            print(f"  {i}/{len(origins)} 駅", flush=True)

    # 既存を読み、追加ぶんを入れ替える（何度流しても二重にならない）
    existing = list(csv.DictReader(OUT.open(encoding="utf-8-sig")))
    keep = [r for r in existing if r["school_number"] not in access]
    dropped = len(existing) - len(keep)

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["from_station", "school_number", "minutes",
                                          "via_station", "access_mode"])
        w.writeheader()
        w.writerows(keep + rows)

    print(f"\n既存 {len(keep):,}行 + 高専 {len(rows):,}行 = {len(keep)+len(rows):,}行 -> {OUT.name}")
    if dropped:
        print(f"  （前回の高専ぶん {dropped:,}行 を入れ替えました）")
    for sn in access:
        n = sum(1 for r in rows if r["school_number"] == sn)
        name = next(r["name"] for r in extra if r["school_number"] == sn)
        print(f"  {name}: {n:,}駅から到達可能")


if __name__ == "__main__":
    main()
