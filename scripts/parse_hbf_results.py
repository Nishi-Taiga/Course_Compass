#!/usr/bin/env python3
"""高野連の試合結果から、都立各校が「どこまで勝ち上がったか」を出す。

    python3 scripts/fetch_hbf_results.py     # 先に取得
    python3 scripts/parse_hbf_results.py

出力: data/seed/school_baseball_results.csv
      （school_club_achievements.csv と同じ列。あとで合流させられる）

## 何を取り、何を捨てるか

取るのは **学校名・ラウンド・スコア** だけ。

⚠️ 元ページには出場選手の氏名が載っている（投手・捕手・本塁打・二塁打）。
   **一切読まない。** 抽出の対象を score_table の学校名セルに限定してあるので、
   氏名が混ざる余地がない。伏せ字にするのではなく、最初から触らない。

## 「実績」の作り方

優勝・準優勝だけでは都立の実績にならない（優勝校はほぼ私立）。
1試合ずつ見て、各校がその大会で**最も先まで進んだラウンド**を実績にする。

  決勝で勝った       → 優勝
  決勝で負けた       → 準優勝
  準決勝で負けた     → ベスト4
  準々決勝で負けた   → ベスト8
  それ以外          → 「三回戦進出」のように、出場した最後のラウンド

⚠️ 「一回戦敗退」は実績として書き出さない。ほぼ全校に付く値で、
   持っていても学校を選ぶ材料にならないうえ、負けたことだけを
   並べることになるため。出場した事実は「一回戦出場」として残す。
"""

from __future__ import annotations

import base64
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_clubs import decode_html, strip_noise, text_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
HBF = ROOT / "data" / "fetched" / "hbf"
INDEX_CSV = HBF / "index.csv"
OUT = SEED / "school_baseball_results.csv"

SOURCE = "一般財団法人 東京都高等学校野球連盟 試合結果"

# ラウンドの並び。数字が大きいほど先まで進んでいる
ROUNDS = [
    ("一回戦", 1), ("１回戦", 1), ("1回戦", 1),
    ("二回戦", 2), ("２回戦", 2), ("2回戦", 2),
    ("三回戦", 3), ("３回戦", 3), ("3回戦", 3),
    ("四回戦", 4), ("４回戦", 4), ("4回戦", 4),
    ("五回戦", 5), ("５回戦", 5), ("5回戦", 5),
    ("準々決勝", 6), ("準決勝", 7), ("決勝", 8),
]
ROUND_NAME = {1: "一回戦", 2: "二回戦", 3: "三回戦", 4: "四回戦", 5: "五回戦",
              6: "準々決勝", 7: "準決勝", 8: "決勝"}

SCORE_TABLE_RE = re.compile(r'class="score_table"')
# ⚠️ 後攻の class は kouko ではなく **koko**（サイト側の綴り）。
#    kouko だけを見ていると、どのページからも1試合も取れない。
NAME_RE = re.compile(r'<td class="(?:senko|kouko|koko)_name">(?P<n>[^<]*)</td>')
TOTAL_RE = re.compile(r'<td class="gokei[^"]*">(?P<v>[^<]*)</td>')
NOTE_RE = re.compile(r"【(?P<r>[^】]{2,10})】")
MEET_RE = re.compile(r"<li[^>]*>([^<]*大会[^<]*)</li>")

# 「立川国際・東村山・府中・都武蔵」のような合同チームがある。
# 1チームとして扱うと4校ぶんの実績が消えるので、校名ごとに分けて数える。
TEAM_SPLIT_RE = re.compile(r"[・､,／/]|\s{2,}")


def split_team(name: str) -> list[str]:
    parts = [re.sub(r"\s+", "", p) for p in TEAM_SPLIT_RE.split(name)]
    return [p for p in parts if p]


def round_of(text: str) -> int | None:
    for word, n in ROUNDS:
        if word in text:
            return n
    return None


def year_of(url: str) -> str:
    """日付ページのURLに埋まっている年を取り出す。

    トークンは base64url の JSON（{"sel":102,"y":2026,"m":7,"d":4,...}）。
    年度は「4〜3月」なので、1〜3月の試合は前年度として数える。
    """
    token = url.rstrip("/").split("/")[-1]
    pad = "=" * (-len(token) % 4)
    try:
        obj = json.loads(base64.urlsafe_b64decode(token + pad).decode("utf-8", "replace"))
    except Exception:
        return ""
    y, m = int(obj.get("y", 0)), int(obj.get("m", 0))
    if not y:
        return ""
    nendo = y - 1 if m and m <= 3 else y
    return f"令和{nendo - 2018}年度"          # 2019 = 令和元年


def parse_page(html: str) -> list[dict]:
    """1日ぶんのページから試合を拾う。学校名・ラウンド・スコアだけ。

    1ページに複数試合が並ぶ。score_table の位置で区切り、
    その手前を大会名、その後ろを校名・得点・備考として読む。
    """
    body = strip_noise(html)
    spots = [m.start() for m in SCORE_TABLE_RE.finditer(body)]
    games = []

    for i, pos in enumerate(spots):
        head = body[(spots[i - 1] if i else 0):pos]
        tail = body[pos:(spots[i + 1] if i + 1 < len(spots) else len(body))]

        names = [n.strip() for n in NAME_RE.findall(tail) if n.strip()]
        totals = [t.strip().replace("&nbsp;", "") for t in TOTAL_RE.findall(tail)]
        totals = [t for t in totals if t and t != "計"]
        if len(names) < 2 or len(totals) < 2:
            continue

        note = NOTE_RE.search(text_of(tail))
        rnd = round_of(note.group("r")) if note else None

        meet = ""
        for cand in MEET_RE.findall(head):
            cand = re.sub(r"\s+", " ", cand).strip()
            if "大会" in cand and len(cand) > 6:
                meet = cand           # 直前のものを採る（同じ日に東西が並ぶため）
        try:
            s1, s2 = int(totals[0]), int(totals[1])
        except ValueError:
            continue

        games.append({
            "meet": meet, "round": rnd,
            "home": names[0], "home_score": s1,
            "away": names[1], "away_score": s2,
        })
    return games


def main() -> None:
    if not INDEX_CSV.is_file():
        sys.exit(f"{INDEX_CSV} がありません。先に fetch_hbf_results.py を実行してください")

    master = {r["name"]: r for r in csv.DictReader(
        (SEED / "schools_master.csv").open(encoding="utf-8-sig"))}

    index = list(csv.DictReader(INDEX_CSV.open(encoding="utf-8-sig")))
    # (学校, 大会, 年度) -> 最も先まで進んだラウンドと、そこで勝ったか
    best: dict[tuple, dict] = {}
    games_seen = pages = 0
    unknown_names: set[str] = set()

    for row in index:
        path = HBF / row["file"]
        if not path.is_file():
            continue
        pages += 1
        year = year_of(row["url"])
        for g in parse_page(decode_html(path.read_bytes())):
            games_seen += 1
            if g["round"] is None:
                continue
            meet = g["meet"] or row["meet"]
            for side, opp in (("home", "away"), ("away", "home")):
                won = g[f"{side}_score"] > g[f"{opp}_score"]
                for name in split_team(g[side]):
                    if name not in master:
                        if name:
                            unknown_names.add(name)
                        continue
                    key = (name, meet, year)
                    cur = best.get(key)
                    if cur is None or g["round"] > cur["round"] or (
                            g["round"] == cur["round"] and won and not cur["won"]):
                        best[key] = {"round": g["round"], "won": won}

    rows = []
    for (name, meet, year), v in sorted(best.items()):
        r, won = v["round"], v["won"]
        if r == 8:
            rank = "優勝" if won else "準優勝"
        elif r == 7:
            rank = "ベスト4" if not won else "決勝進出"
        elif r == 6:
            rank = "ベスト8" if not won else "ベスト4"
        else:
            # 「そのラウンドまで到達した」で言い方を揃える。勝った試合の次の
            # ラウンドまで進んでいる。負けた試合のラウンドが到達点。
            # 進出/出場を混ぜると「二回戦進出」と「二回戦出場」が併存して読みにくい。
            reached = r + 1 if won else r
            rank = "一回戦出場" if reached == 1 else f"{ROUND_NAME.get(reached, '')}進出"
        rows.append({
            "school_number": master[name]["school_number"],
            "school": name,
            "year": year,
            "meet": meet,
            "sport": "硬式野球",
            "event": "",
            "division": "",
            "rank": rank,
            "source": SOURCE,
        })

    # 個人が特定できる情報が混ざっていないことを、書き出す前に確かめる。
    # 元ページには選手の氏名が載っているので、抽出の範囲を間違えると入り込む。
    #
    # ⚠️ 見るのは学校名・順位・種目だけ。大会名や出典はこちらで組み立てた
    #    文字列で、「東京都 高等学校」のように漢字＋空白＋漢字を含むため、
    #    氏名の判定に混ぜると誤検知する。
    person = re.compile(r"さん|君|くん|選手(?![権団])|投手|捕手|本塁打")
    checked = ("school", "rank", "event", "division")
    leaked = [f"{r['school']} {k}={v}" for r in rows for k in checked
              if (v := r.get(k)) and person.search(str(v))]
    if leaked:
        print("⚠️ 個人名らしき文字列が出力に含まれています。中止します。")
        for x in leaked[:10]:
            print("   ", x)
        sys.exit(1)
    print("個人情報の検査: 問題なし（学校名・ラウンド・スコアのみ）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "school_number", "school", "year", "meet", "sport", "event",
            "division", "rank", "source"])
        w.writeheader()
        w.writerows(rows)

    print(f"日付ページ {pages} / 試合 {games_seen:,}")
    print(f"{OUT.relative_to(ROOT)} -> {len(rows)}件 / 都立 {len({r['school'] for r in rows})}校")
    print(f"  マスタに無い学校名（私立など） {len(unknown_names)}件")
    import collections
    for rank, n in collections.Counter(r["rank"] for r in rows).most_common():
        print(f"    {rank:12} {n}件")


if __name__ == "__main__":
    main()
