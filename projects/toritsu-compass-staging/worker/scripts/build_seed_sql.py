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

# 部活の取得日。出典と一緒に持たせる（いつ時点の情報かが分からないと使えない）
FETCHED_AT = "2026-08-14"


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

    # 都教委の一覧に載らない学校（産技高専）。schools_master.csv は都教委CSVから
    # 生成されるので直接書き足すと再生成で消える。別ファイルにして合流させる。
    extra_csv = seed_dir / "extra_schools.csv"
    extra_schools = read_csv(extra_csv) if extra_csv.is_file() else []
    for r in extra_schools:
        master.append({
            "school_number": r["school_number"], "name": r["name"], "name_kana": "",
            "ward": r["ward"], "postal_code": "", "address": r["address"], "phone": "",
            "course_types": r["course_types"], "departments": r["departments"],
            "students_fulltime": "", "designation": "",
        })

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
        "DELETE FROM school_achievements;",
        "DELETE FROM school_uniforms;",
        "DELETE FROM commute_times;",
        "DELETE FROM ward_stations;",
        "DELETE FROM stations;",
        "DELETE FROM school_stats;",
        "DELETE FROM schools;",
        "",
    ]

    # --- schools ---
    extra_by_number = {r["school_number"]: r for r in extra_schools}
    school_rows = []
    for r in master:
        name = r["name"].strip()
        sc = scores.get(name, {})
        # 高専は目安点を持たない。入試の満点も配点も都立高校と違うため、
        # 同じ目安点を当てると過大評価になる（build_kosen.py の注記参照）
        ex = extra_by_number.get(r["school_number"])
        if ex:
            sc = {"selection_type": ex["selection_type"],
                  "selection_note": ex["selection_note"]}
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
            sql_str(extra_by_number.get(r["school_number"], {}).get("source_master") or SOURCE_MASTER),
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
    commute_csv = seed_dir / "school_commute_times.csv"

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
        # 出発駅は駅マスタ（都内647駅）に載っているものだけ入れる。
        # 到着側は都県境の学校のため神奈川等も混ざるが、そちらは via_station として
        # 文字列で持つだけなので外部キーの対象にしない。
        commute = [r for r in commute if r["from_station"] in station_names]

        emit_inserts(out, "commute_times",
                     ["from_station", "school_number", "minutes", "via_station", "access_mode"],
                     [[sql_str(r["from_station"]), sql_str(r["school_number"]),
                       sql_int(r["minutes"]), sql_str(r["via_station"]),
                       sql_str(r["access_mode"])]
                      for r in commute],
                     per_stmt=ROWS_PER_INSERT_BULK)
        counts["commute_times"] = len(commute)
    else:
        out.append("-- 通学時間系は未生成（scripts/extract_prototype_data.py を先に実行）")
        out.append("")

    # --- 部活動（Step6） ---
    # 全日制・定時制・高専の3系統。取得の経路が違うのでCSVが分かれている
    club_files = [seed_dir / "school_clubs.csv",
                  seed_dir / "school_clubs_teiji.csv",
                  seed_dir / "extra_school_clubs.csv"]
    clubs_csv = club_files[0]
    if clubs_csv.is_file():
        clubs = [r for f in club_files if f.is_file() for r in read_csv(f)]
        # 正規化辞書（西の監修済み・2026-08-19）。raw_name → normalized + gender。
        # raw_name は書き換えない。normalized と gender を足すだけ（仕様書§6.2）
        norm_csv = seed_dir / "club_normalize.csv"
        norm = ({r["raw_name"]: (r["normalized"], r.get("gender") or "")
                 for r in read_csv(norm_csv)} if norm_csv.is_file() else {})
        known = {r["school_number"] for r in master}
        unknown = sorted({r["school_number"] for r in clubs} - known)
        if unknown:
            # 黙って落とすと「部活が無い学校」に化ける。名寄せ漏れは必ず止める
            sys.exit(f"school_clubs.csv に未知の学校番号: {unknown}")
        emit_inserts(out, "school_clubs",
                   ["school_number", "raw_name", "normalized", "gender", "category",
                    "source_url", "fetched_at"],
                   [[sql_str(r["school_number"]), sql_str(r["raw_name"]),
                     sql_str(norm.get(r["raw_name"], ("", ""))[0]),  # 監修済みの種目名
                     sql_str(norm.get(r["raw_name"], ("", ""))[1]),  # 男子 / 女子 / 男女
                     sql_str(r.get("category") or ""), sql_str(r.get("source_url") or ""),
                     sql_str(FETCHED_AT)]
                    for r in clubs],
                   per_stmt=ROWS_PER_INSERT_BULK)
        counts["school_clubs"] = len(clubs)
    else:
        out.append("-- school_clubs は未投入（scripts/extract_school_clubs.py を先に実行）")
        out.append("")

    # --- 部の実績 ---
    # 出典の異なる6系統。すべて同じ列にそろえてある。
    # ⚠️ 生徒の氏名・学年・記録は元データの時点で読み取っていない。
    #    ここでも列を作らない（列を作って空にすると後から埋められてしまう）。
    #
    # ⚠️ ここの一覧は attribute_achievements.py の EXTRA_SOURCES と**別物**。
    #    向こうに足してもここに足さないと、CSVには入るのにAPIには出ない。
    #    （演劇を足したとき実際にそうなった。CSVは33件あるのにDBには0件だった）
    ach_files = [
        (seed_dir / "school_club_achievements.csv", "東京都高等学校体育連盟"),
        (seed_dir / "school_baseball_results.csv", "東京都高等学校野球連盟"),
        (seed_dir / "school_suisou_results.csv", "東京都高等学校吹奏楽連盟"),
        (seed_dir / "school_ifac_results.csv", "高校生国際美術展"),
        (seed_dir / "school_engeki_results.csv", "東京都高校演劇研究会"),
        (seed_dir / "school_dance_results.csv", "日本高校ダンス部選手権"),
    ]
    ach = []
    for path, org in ach_files:
        if not path.is_file():
            continue
        for r in read_csv(path):
            ach.append({**r, "source_org": org})
    if ach:
        known = {r["school_number"] for r in master}
        unknown = sorted({r["school_number"] for r in ach} - known)
        if unknown:
            sys.exit(f"実績CSVに未知の学校番号: {unknown}")
        # 氏名らしき列が紛れ込んでいないかの最終検査
        forbidden = {"name", "選手名", "氏名", "grade", "学年", "record", "記録"}
        for r in ach[:1]:
            bad = forbidden & set(r)
            if bad:
                sys.exit(f"実績CSVに個人情報の列が含まれています: {bad}")
        emit_inserts(out, "school_achievements",
                     ["school_number", "year", "meet", "sport", "event",
                      "division", "rank", "source_org", "source"],
                     [[sql_str(r["school_number"]), sql_str(r.get("year") or ""),
                       sql_str(r.get("meet") or ""), sql_str(r.get("sport") or ""),
                       sql_str(r.get("event") or ""), sql_str(r.get("division") or ""),
                       sql_str(r.get("rank") or ""), sql_str(r["source_org"]),
                       sql_str(r.get("source") or "")]
                      for r in ach],
                     per_stmt=ROWS_PER_INSERT_BULK)
        counts["school_achievements"] = len(ach)
    else:
        out.append("-- school_achievements は未投入")
        out.append("")

    # --- 制服 ---
    uni_csv = seed_dir / "school_uniforms.csv"
    if uni_csv.is_file():
        uni = [r for r in read_csv(uni_csv) if r.get("uniform_type")]
        known = {r["school_number"] for r in master}
        uni = [r for r in uni if r["school_number"] in known]
        emit_inserts(out, "school_uniforms",
                     ["school_number", "uniform_type", "slacks_skirt_choice",
                      "quote", "source"],
                     [[sql_str(r["school_number"]), sql_str(r["uniform_type"]),
                       "1" if r.get("slacks_skirt_choice") else "0",
                       sql_str(r.get("quote") or ""), sql_str(r.get("source") or "")]
                      for r in uni])
        counts["school_uniforms"] = len(uni)
    else:
        out.append("-- school_uniforms は未投入")
        out.append("")

    dest = worker_dir / "seed.sql"
    dest.write_text("\n".join(out), encoding="utf-8", newline="\n")

    print(f"生成: {dest}")
    print(f"  schools       : {len(school_rows)} 行")
    print(f"  school_stats  : {len(stat_rows)} 行")
    print(f"  stations      : {counts['stations']} 行")
    print(f"  ward_stations : {counts['ward_stations']} 行")
    print(f"  commute_times : {counts['commute_times']} 行")
    print(f"  school_clubs  : {counts.get('school_clubs', 0)} 行")
    print(f"  実績          : {counts.get('school_achievements', 0)} 行")
    print(f"  制服          : {counts.get('school_uniforms', 0)} 行")
    print(f"  指定区分あり  : {sum(1 for r in master if r['designation'].strip())} 校")
    print(f"  名寄せ漏れ    : 0 件")


if __name__ == "__main__":
    main()
