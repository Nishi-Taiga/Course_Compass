#!/usr/bin/env python3
"""各校公式サイトの部活動ページから、部の実績を取り出す。

都高体連の記録（parse_kotairen_results.py）を主とし、これはその補完。
連盟の一覧に載らない範囲——都大会の5位以下、高体連の管轄外（野球=高野連、
吹奏楽=高文連など）——を各校の自己申告から拾う。

**目標と実績を必ず分ける。** 部活動ページは
    「関東大会出場を目標にし、日々練習に励んでいます」（＝目標）
    「令和2年度は東京都ベスト16」                      （＝実績）
が同じページに混在する。前者を実績として出すと、行っていない大会に
行ったことにしてしまう。年度の表記があるかどうかが両者を分ける決め手なので、
**年度つきの記述だけ**を採る。それでも「令和5年度は目標にしていた西東京ベスト4」
のような書き方が残るため、目標語を含む文は要確認として出力し、自動採用しない。

出力: data/seed/school_club_achievements_sites.csv
"""

from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
CLUBS = BASE / "data" / "fetched" / "clubs"
OUT = SEED / "school_club_achievements_sites.csv"

YEAR = re.compile(r"(?:令和|平成)\s*([0-9０-９〇一二三四五六七八九十元]+)\s*年")
RANK = re.compile(r"優勝|準優勝|ベスト\s*[0-9０-９]+|第?\s*[0-9０-９]+\s*位|入賞|金賞|銀賞|銅賞")
GOAL = re.compile(r"目標|目指|めざ|向けて|挑戦|臨み|なるよう|したい|できるよう")
# 「活動日（令和8年度）」のような欄見出しが年度として拾われるのを防ぐ
FIELD = re.compile(r"活動日|活動内容|活動紹介|練習日|指導方針|部員数|活動場所")
CLUB = re.compile(r"((?:男子|女子)?[ぁ-んァ-ヴ一-龥ー]{2,10}?(?:部|班|同好会))")
# 「周囲から応援される部」「夏休み体験入部」のような地の文の断片を部活名として
# 拾わないための語彙。この語を含まないものは部活名として採らない
CLUB_WORD = re.compile(
    r"サッカー|野球|バスケ|バレー|テニス|卓球|バドミントン|陸上|水泳|競泳|水球|柔道|剣道|"
    r"弓道|なぎなた|ソフト|ハンド|ラグビー|体操|ダンス|チア|空手|相撲|レスリング|"
    r"フェンシング|ボート|カヌー|自転車|登山|山岳|少林寺|アーチェリー|ホッケー|ラクロス|"
    r"ワンダーフォーゲル|吹奏楽|管弦楽|合唱|軽音|演劇|美術|書道|写真|将棋|囲碁|かるた|"
    r"百人一首|放送|新聞|茶道|華道|文芸|園芸|調理|商業|簿記|映像|情報|クイズ|パソコン|"
    r"科学|生物|物理|化学|地学|天文|数学|英語|漫画|アニメ|鉄道|手芸|家庭|ボランティア")
MEET = [("全国大会", r"全国大会|インターハイ|インハイ|全国高等学校総合体育大会|甲子園|全国選抜"),
        ("関東大会", r"関東大会|関東高等学校|関東選抜"),
        ("東京都大会", r"東京都|都大会|都立|西東京|東東京|支部")]
# 「インターハイ予選」「関東大会予選」は東京都内の予選であって本大会ではない。
# 大会名だけ見て全国・関東と判定すると、出ていない大会に出たことにしてしまう
QUALIFIER = re.compile(r"予選|地区大会|支部大会|都大会予選")


def decode(path: Path) -> str:
    raw = path.read_bytes()
    enc = "shift_jis" if re.search(rb'charset=["\']?(shift_jis|sjis|x-sjis)', raw, re.I) else "utf-8"
    t = html.unescape(re.sub(rb"<script.*?</script>|<style.*?</style>", b"",
                             raw, flags=re.S | re.I).decode(enc, "ignore"))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def meet_of(text: str) -> str:
    """大会の格。予選は本大会に格上げしない。

    「インターハイ予選ベスト4」は都内での成績であって全国大会の実績ではない。
    予選と書いてあれば、大会名が全国・関東でも東京都大会として扱う。
    """
    for name, pat in MEET:
        if re.search(pat, text):
            if name in ("全国大会", "関東大会") and QUALIFIER.search(text):
                return "東京都大会（予選）"
            return name
    return ""


def main() -> None:
    if not CLUBS.is_dir():
        sys.exit(f"{CLUBS} がありません。fetch_school_clubs.py を先に実行してください。")
    # 台帳は既定で data/seed/school_sites.csv。clubs_url を持つ版が要る
    ledger = Path(sys.argv[1]) if len(sys.argv) > 1 else SEED / "school_sites.csv"
    reader = csv.DictReader(open(ledger, encoding="utf-8"))
    if "clubs_url" not in (reader.fieldnames or []):
        sys.exit(f"{ledger} に clubs_url がありません。"
                 "部活ページ版の台帳（PR #4）を指定してください。")
    sites = {r["school_number"]: r for r in reader}

    rows = []
    for path in sorted(CLUBS.glob("*.html")):
        number = path.name.split("_")[0]
        info = sites.get(number, {})
        text = decode(path)
        for m in re.finditer(r"[^。！\n]{5,120}", text):
            sent = m.group(0).strip(" ・")
            if not (YEAR.search(sent) and RANK.search(sent)):
                continue
            # 1文に複数の年度が並ぶ書き方（「令和2年度は都ベスト16 ・令和3年度は
            # 都ベスト64」）は、どの順位がどの年度のものか機械的に決められない。
            # 先頭の年度を当てると別の年の実績にすり替わるので、人の確認に回す
            multi_year = len({y.group(0) for y in YEAR.finditer(sent)}) > 1
            flag = ("要確認" if (GOAL.search(sent) or FIELD.search(sent) or multi_year)
                    else "OK")
            year = YEAR.search(sent)
            # 部活名は「文の先頭」ではなく「実績が書かれている位置」の直前から探す。
            # 文の切り出し位置は実際の記述より前に始まることがあり、そのまま遡ると
            # 隣の部の名前を拾う（狛江で女子バレーの実績が男子バレーに付いた）
            anchor = m.start() + year.start()
            before = text[max(0, anchor - 300):anchor]
            clubs = [c for c in CLUB.findall(before) if CLUB_WORD.search(c)]
            rows.append({
                "school_number": number,
                "school": info.get("name", ""),
                "club": clubs[-1] if clubs else "",
                "year": f"令和{year.group(1)}年度" if "令和" in year.group(0) else year.group(0),
                "meet": meet_of(sent),
                "text": sent,
                "flag": flag,
                "source": info.get("clubs_url", ""),
            })

    seen, out = set(), []
    for r in rows:
        key = (r["school_number"], r["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)

    fields = ["school_number", "school", "club", "year", "meet", "text", "flag", "source"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    ok = [r for r in out if r["flag"] == "OK"]
    print(f"候補 {len(out)}件 / {len({r['school_number'] for r in out})}校")
    print(f"  自動採用可 (OK)  : {len(ok)}件 / {len({r['school_number'] for r in ok})}校")
    print(f"  要確認           : {len(out) - len(ok)}件")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
