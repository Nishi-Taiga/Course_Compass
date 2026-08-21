#!/usr/bin/env python3
"""大会実績を「部の成績」に整え、個人が特定できる情報が無いことを検査する。

    python3 scripts/attribute_achievements.py

出力:
    data/seed/school_club_achievements_attributed.csv

## やっていること

1. **個人が特定できる情報が入っていないかを検査する。**
   入っていたら異常終了する。個人種目（陸上・水泳・テニスの単など）は
   氏名が載りやすいので、機械的に止められるようにしておく。

2. **競技名から部を割り当てる。**
   実績CSVは競技（sport / event）までしか持たず、どの部の成績かが
   入っていない。school_clubs.csv の実在する部と突き合わせて club 列を作る。
   これで「個人種目でも部の成績として見せる」ことができる。

## 判断したこと

⚠️ **個人名は「伏せる」のではなく、最初から持たない。**
   伏せ字にして列を残すと、後から誰かが元データで埋め直せてしまう。
   西さんの判断（氏名・学年・記録を保持しない）どおり、列ごと持たない。
   このスクリプトはその状態が崩れていないかを見張る役。

⚠️ 部を割り当てられない実績も**捨てない**。club を空のままにして残す。
   捨てると「実績が無い学校」に見えるが、実際は名寄せできなかっただけ。
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
ACHIEVE = SEED / "school_club_achievements.csv"

# 連盟ごとにファイルが分かれている。管轄が違うので取得の経路も別。
#   高体連   … school_club_achievements.csv（運動部の大半）
#   高野連   … school_baseball_results.csv（硬式野球）
#   吹奏楽連盟 … school_suisou_results.csv（吹奏楽コンクール）
#   国際美術展 … school_ifac_results.csv（書道・美術）
#   高文連系 … school_engeki_results.csv（演劇 都大会）
#   ダンス選手権 … school_dance_results.csv（ダンス。どの連盟にも属さない）
EXTRA_SOURCES = [
    SEED / "school_baseball_results.csv",
    SEED / "school_suisou_results.csv",
    SEED / "school_ifac_results.csv",
    SEED / "school_engeki_results.csv",
    SEED / "school_dance_results.csv",
]
CLUBS = SEED / "school_clubs.csv"
CLUBS_TEIJI = SEED / "school_clubs_teiji.csv"
EXTRA_CLUBS = SEED / "extra_school_clubs.csv"
OUT = SEED / "school_club_achievements_attributed.csv"

# 個人が特定できる情報。見つけたら止める。
#   - 「氏名」「選手名」などの列見出し
#   - 本文中の「◯◯ ◯◯さん」「◯◯君」「◯◯選手」
PERSON_COLUMNS = ("氏名", "名前", "選手名", "name", "student", "学年", "grade")
PERSON_TEXT_RE = re.compile(r"(さん|君|くん|選手)(?![権団])|[一-龥]{1,2}\s[一-龥]{1,2}\s*(?:さん|君|選手)")

# 個人種目の目印。順位だけを残し、誰が出たかは持たない
INDIVIDUAL_RE = re.compile(r"個人|シングルス|ダブルス|単|複|の部")


# 種目名から競技を補う。実績CSVは sport が空で event に種目名だけ、という行が多い
# （「200m個人メドレー」「個人ロード・レース」）。そのままでは部に結び付かない。
SPORT_HINTS = [
    (re.compile(r"メドレー|自由形|背泳|平泳|バタフライ|水球|飛込"), "水泳"),
    (re.compile(r"ロード・?レース|トラック・?レース|自転車"), "自転車"),
    (re.compile(r"機械体操|体操|跳馬|平均台|鉄棒|あん馬"), "体操"),
    (re.compile(r"\d+\s*m|走(?:幅|高)跳|砲丸|やり投|円盤|駅伝|ハードル|リレー"), "陸上競技"),
    (re.compile(r"シングルス|ダブルス|団体戦"), ""),          # 競技はここでは決まらない
    (re.compile(r"型|組手"), "空手"),
    (re.compile(r"かるた|百人一首"), "かるた"),
    (re.compile(r"アーチェリー"), "アーチェリー"),
    (re.compile(r"ボート|漕艇"), "ボート"),
    (re.compile(r"フェンシング"), "フェンシング"),
    (re.compile(r"ウエイト|重量挙"), "ウエイトリフティング"),
    (re.compile(r"山岳|登山|クライミング"), "山岳"),
    (re.compile(r"新体操"), "新体操"),
    (re.compile(r"ライフル|射撃"), "ライフル射撃"),
    (re.compile(r"相撲"), "相撲"),
]


def guess_sport(row: dict) -> str:
    """sport 列が空でも、種目名から競技を推し量る。"""
    text = f"{row.get('sport') or ''} {row.get('event') or ''}"
    for pat, sport in SPORT_HINTS:
        if pat.search(text) and sport:
            return sport
    return ""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"[\s　・()（）]", "", s)


def club_base(name: str) -> str:
    """部活名から種目部分を取り出す。「男子バスケットボール部」→「バスケットボール」。"""
    s = norm(name)
    s = re.sub(r"^(男子|女子|男女)", "", s)
    s = re.sub(r"(部|班|同好会|愛好会|クラブ)$", "", s)
    return s


def load_clubs() -> dict[str, list[tuple[str, str]]]:
    """学校番号 -> [(部活名, 種目部分)]。定時制・高専ぶんも合わせて読む。"""
    out: dict[str, list[tuple[str, str]]] = {}
    for path in (CLUBS, CLUBS_TEIJI, EXTRA_CLUBS):
        if not path.is_file():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            base = club_base(r["raw_name"])
            if base:
                out.setdefault(r["school_number"], []).append((r["raw_name"], base))
    return out


def check_privacy(rows: list[dict], fieldnames: list[str]) -> list[str]:
    """個人が特定できる情報を探す。見つけたものを説明として返す。"""
    problems = []
    for col in fieldnames:
        if any(k in col.lower() for k in (c.lower() for c in PERSON_COLUMNS)):
            problems.append(f"列「{col}」は個人の情報にあたります")

    for i, r in enumerate(rows, 2):        # 2行目からがデータ
        for col, v in r.items():
            if v and PERSON_TEXT_RE.search(str(v)):
                problems.append(f"{i}行目 {col}: 個人名らしき表記「{str(v)[:40]}」")
    return problems


def main() -> None:
    rows = list(csv.DictReader(ACHIEVE.open(encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())

    for path in EXTRA_SOURCES:
        if not path.is_file():
            continue
        extra = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        if not extra:
            continue
        # 列が食い違ったまま混ぜると、後段で静かに欠損する
        unknown_cols = set(extra[0].keys()) - set(fieldnames)
        if unknown_cols:
            sys.exit(f"{path.name} に想定外の列: {sorted(unknown_cols)}")
        rows.extend(extra)
        print(f"合流: {path.name} {len(extra)}件")

    problems = check_privacy(rows, fieldnames)
    if problems:
        print("⚠️ 個人が特定できる情報が含まれています。取り込みを中止します。")
        for p in problems[:20]:
            print("   ", p)
        sys.exit(1)
    print(f"個人情報の検査: 問題なし（{len(rows)}件 / 列 {len(fieldnames)}）")

    clubs = load_clubs()
    matched = unmatched = 0
    individual = 0
    out_rows = []

    for r in rows:
        sport = norm(r.get("sport") or "") or norm(guess_sport(r)) or norm(r.get("event") or "")
        is_individual = bool(INDIVIDUAL_RE.search((r.get("event") or "") + (r.get("division") or "")))
        individual += 1 if is_individual else 0

        club = ""
        for raw_name, base in clubs.get(r["school_number"], []):
            if not base:
                continue
            # 競技名に部の種目が含まれるか、その逆。長い一致を優先する
            if base in sport or (len(base) >= 3 and sport and sport in base):
                if len(base) > len(club_base(club or "")):
                    club = raw_name
        if club:
            matched += 1
        else:
            unmatched += 1

        out_rows.append({
            **r,
            "club": club,
            # 個人種目でも「部の成績」として見せる。誰が出たかは持っていない
            "is_individual_event": "1" if is_individual else "0",
        })

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames + ["club", "is_individual_event"])
        w.writeheader()
        w.writerows(out_rows)

    print(f"{OUT.relative_to(ROOT)} -> {len(out_rows)}件")
    print(f"  部を割り当てられた   {matched}件")
    print(f"  割り当てられなかった {unmatched}件（club は空のまま残す）")
    print(f"  うち個人種目        {individual}件（順位だけを保持。氏名・学年・記録は持たない）")


if __name__ == "__main__":
    main()
