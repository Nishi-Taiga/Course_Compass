#!/usr/bin/env python3
"""data/seed/*.csv から D1 投入用の seed.sql を生成する。

    python scripts/build_seed_sql.py

倍率CSVは学校を「名前」でしか持っていないため、学校マスタの name → school_number で
名寄せする。1件でも解決できない名前があれば、黙って落とさずエラーで止める
（サイレントな取りこぼしが一番タチが悪いため）。

通学時間系（stations / ward_stations / commute_times）は
scripts/extract_prototype_data.py が prototype から取り出したCSVを使う。
無ければその3テーブルだけスキップする（Step3以前でも動くように）。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

YEARS = ["r4", "r5", "r6", "r7", "r8"]

# 出典表示は審査観点のひとつ（「この数字は都教委の公開資料由来」が見えること）。
# データと一緒にDBへ入れておき、APIのレスポンスまで運ぶ。
SOURCE_MASTER = "東京都教育委員会 都立学校一覧"
SOURCE_RATIO = {
    "r4": "東京都教育委員会 令和4年度 応募状況",
    "r5": "東京都教育委員会 令和5年度 応募状況",
    "r6": "東京都教育委員会 令和6年度 応募状況",
    "r7": "東京都教育委員会 令和7年度 応募状況",
    "r8": "東京都教育委員会 令和8年度 応募状況",
}

# 目安点は現時点では公開データの層別に置いた仮値。
# 西が2026-08-14に実値を入れる予定で、そのとき出典もあわせて差し替える。
SOURCE_TARGET_SCORE = "公開データの層別による暫定値（2026-08-14に実値へ差し替え予定）"

# 1文あたりの VALUES 数。commute_times は3万行あるので大きめに束ねる。
ROWS_PER_INSERT = 100
ROWS_PER_INSERT_BULK = 250


def find_repo_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "data" / "seed" / "schools_master.csv").is_file():
            return d
    sys.exit("data/seed/schools_master.csv が見つかりません。リポジトリ内で実行してください。")


def read_csv(path: Path) -> list[dict[str, str]]:
    # 都教委CSVは BOM 付きのことがあるので utf-8-sig で読む
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sql_str(value: str | None) -> str:
    """SQL文字列リテラル。空文字は NULL 扱いにする。"""
    if value is None:
        return "NULL"
    v = value.strip()
    if v == "":
        return "NULL"
    return "'" + v.replace("'", "''") + "'"


def sql_int(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "NULL"
    try:
        return str(int(float(str(value).strip())))
    except ValueError:
        return "NULL"


def sql_real(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "NULL"
    try:
        return repr(float(str(value).strip()))
    except ValueError:
        return "NULL"


def emit_inserts(out, table, columns, rows, per_stmt=ROWS_PER_INSERT) -> None:
    """複数行 INSERT にまとめて書き出す。1行ずつだと3万行が終わらない。"""
    if not rows:
        out.append(f"-- {table}: 投入データなし")
        out.append("")
        return
    cols = ", ".join(columns)
    for i in range(0, len(rows), per_stmt):
        chunk = rows[i : i + per_stmt]
        values = ",\n  ".join("(" + ", ".join(r) + ")" for r in chunk)
        out.append(f"INSERT INTO {table} ({cols}) VALUES\n  {values};")
    out.append("")


def main() -> None:
    here = Path(__file__).resolve()
    worker_dir = here.parents[1]
    root = find_repo_root(here.parent)
    seed_dir = root / "data" / "seed"

    master = read_csv(seed_dir / "schools_master.csv")
    designations = read_csv(seed_dir / "designations.csv")

    # 判定モデル用の値。extract_prototype_data.py が prototype から取り出す。
    scores_csv = seed_dir / "school_scores.csv"
    scores = {r["name"].strip(): r for r in read_csv(scores_csv)} if scores_csv.is_file() else {}

    # --- name -> school_number（重複名があると名寄せが壊れるので検出する） ---
    name_to_number: dict[str, str] = {}
    dupes: list[str] = []
    for r in master:
        name = r["name"].strip()
        if name in name_to_number:
            dupes.append(name)
        name_to_number[name] = r["school_number"].strip()
    if dupes:
        sys.exit(f"学校マスタに重複名: {sorted(set(dupes))}")

    # --- 補助データ（指定区分ランク / レベル帯ドラフト / 指定区分の出典） ---
    rank_by_name = {r["school_name"].strip(): r["designation_rank"] for r in designations}
    src_by_name = {r["school_name"].strip(): r.get("source", "") for r in designations}

    unknown = sorted((set(rank_by_name) | set(scores)) - set(name_to_number))
    if unknown:
        sys.exit(f"マスタに存在しない学校名（designations/school_scores 側）: {unknown}")

    out: list[str] = [
        "-- 自動生成ファイル。直接編集しないこと。",
        "-- 生成: python scripts/build_seed_sql.py",
        "",
        "DELETE FROM sessions;",
        "DELETE FROM school_clubs;",
        "DELETE FROM commute_times;",
        "DELETE FROM ward_stations;",
        "DELETE FROM stations;",
        "DELETE FROM school_stats;",
        "DELETE FROM schools;",
        "",
    ]

    # --- schools ---
    school_rows = []
    for r in master:
        name = r["name"].strip()
        sc = scores.get(name, {})
        school_rows.append([
            sql_str(r["school_number"]),
            sql_str(name),
            sql_str(r["name_kana"]),
            sql_str(r["ward"]),
            sql_str(r["postal_code"]),
            sql_str(r["address"]),
            sql_str(r["phone"]),
            sql_str(r["course_types"]),
            sql_str(r["departments"]),
            sql_int(r["students_fulltime"]),
            sql_str(r["designation"]),
            sql_int(rank_by_name.get(name)),
            sql_int(sc.get("target_score")),
            sql_str(sc.get("selection_type")),
            sql_str(sc.get("selection_note")),
            sql_str(sc.get("score_layer")),
            sql_int(sc.get("no_hs_admission") or 0),
            sql_str(SOURCE_MASTER),
            sql_str(src_by_name.get(name)),
            sql_str(SOURCE_TARGET_SCORE if sc.get("target_score") else None),
        ])
    emit_inserts(out, "schools", [
        "school_number", "name", "name_kana", "ward", "postal_code", "address",
        "phone", "course_types", "departments", "students_fulltime",
        "designation", "designation_rank",
        "target_score", "selection_type", "selection_note", "score_layer",
        "no_hs_admission",
        "source_master", "source_designation", "source_target_score",
    ], school_rows)

    # --- school_stats（倍率 R4〜R8） ---
    stat_rows = []
    unmatched: dict[str, int] = {}
    for year in YEARS:
        for r in read_csv(seed_dir / f"ratios_{year}.csv"):
            school = r["school"].strip()
            number = name_to_number.get(school)
            if number is None:
                unmatched[school] = unmatched.get(school, 0) + 1
                continue
            stat_rows.append([
                sql_str(number),
                sql_str(year),
                sql_str(r["department"]),
                sql_str(r["sub_department"]),
                sql_int(r["capacity"]),
                sql_int(r["applicants"]),
                sql_real(r["ratio"]),
                sql_str(SOURCE_RATIO[year]),
            ])
    if unmatched:
        sys.exit(f"名寄せできなかった学校名（倍率CSV側）: {unmatched}")

    emit_inserts(out, "school_stats", [
        "school_number", "year", "department", "sub_department",
        "capacity", "applicants", "ratio", "source",
    ], stat_rows)

    # --- 通学時間系（extract_prototype_data.py の出力） ---
    stations_csv = seed_dir / "stations.csv"
    wards_csv = seed_dir / "ward_stations.csv"
    commute_csv = seed_dir / "commute_times.csv"

    counts = {"stations": 0, "ward_stations": 0, "commute_times": 0}

    if stations_csv.is_file() and wards_csv.is_file() and commute_csv.is_file():
        stations = read_csv(stations_csv)
        station_names = {r["station_name"] for r in stations}

        emit_inserts(out, "stations", ["station_name", "lat", "lon"],
                     [[sql_str(r["station_name"]), sql_real(r["lat"]), sql_real(r["lon"])]
                      for r in stations])
        counts["stations"] = len(stations)

        ward_rows = read_csv(wards_csv)
        bad_rep = [r["ward"] for r in ward_rows if r["rep_station"] not in station_names]
        if bad_rep:
            sys.exit(f"代表駅が駅マスタに無い区市: {bad_rep}")

        emit_inserts(out, "ward_stations", ["ward", "rep_station"],
                     [[sql_str(r["ward"]), sql_str(r["rep_station"])] for r in ward_rows])
        counts["ward_stations"] = len(ward_rows)

        commute = read_csv(commute_csv)
        bad_from = {r["from_station"] for r in commute} - station_names
        if bad_from:
            sys.exit(f"駅マスタに無い出発駅: {sorted(bad_from)[:10]}")

        emit_inserts(out, "commute_times", ["from_station", "to_ward", "minutes"],
                     [[sql_str(r["from_station"]), sql_str(r["to_ward"]), sql_int(r["minutes"])]
                      for r in commute],
                     per_stmt=ROWS_PER_INSERT_BULK)
        counts["commute_times"] = len(commute)
    else:
        out.append("-- 通学時間系は未生成（scripts/extract_prototype_data.py を先に実行）")
        out.append("")

    out.append("-- school_clubs は未投入（Step2/6）")
    out.append("")

    dest = worker_dir / "seed.sql"
    dest.write_text("\n".join(out), encoding="utf-8", newline="\n")

    print(f"生成: {dest}")
    print(f"  schools       : {len(school_rows)} 行")
    print(f"  school_stats  : {len(stat_rows)} 行")
    print(f"  stations      : {counts['stations']} 行")
    print(f"  ward_stations : {counts['ward_stations']} 行")
    print(f"  commute_times : {counts['commute_times']} 行")
    print(f"  指定区分あり  : {sum(1 for r in master if r['designation'].strip())} 校")
    print(f"  名寄せ漏れ    : 0 件")


if __name__ == "__main__":
    main()
