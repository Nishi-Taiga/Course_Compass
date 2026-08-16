#!/usr/bin/env python3
"""都高体連の記録と、各校サイトの自己申告を突き合わせて食い違いを洗い出す。

併用する以上、両者が違うことを言っている箇所は人が見て決める必要がある。
黙ってどちらかを採ると、保護者に片方の誤りをそのまま渡すことになる。

出す種類は3つ。
  A 順位の相違 … 同じ学校・年度・競技で、連盟の記録と学校の記述の順位が違う
  B 記録に不在 … 学校が関東・全国への出場を書いているが、連盟の該当年度の
                 一覧に同校が見当たらない
  C 未検証     … 連盟の管轄外（野球=高野連、吹奏楽・文化部=高文連など）で
                 そもそも突き合わせようがないもの

Cは「誤り」ではない。連盟の記録では裏が取れない、という区別のために出す。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data" / "seed"
OFFICIAL = SEED / "school_club_achievements.csv"
SITES = SEED / "school_club_achievements_sites.csv"
OUT = SEED / "achievement_conflicts.csv"

# 高体連の管轄外。ここに当たるものは連盟の一覧に載らないのが正常
OUT_OF_SCOPE = re.compile(
    r"野球|甲子園|吹奏楽|コンクール|合唱|演劇|美術|書道|写真|将棋|囲碁|百人一首|"
    r"かるた|放送|新聞|茶道|華道|軽音|ダンス|チア|クイズ|パソコン|科学|生物|物理|化学|"
    r"簿記|商業|映像|調理|情報|駅伝")

# 連盟のPDFを取ってある年度。この外の年度は突き合わせようがない
VERIFIABLE_YEARS = {"令和5年度", "令和6年度", "令和7年度",
                    "令和５年度", "令和６年度", "令和７年度"}

RANK_ORDER = ["優勝", "準優勝", "3位", "4位"]


def norm_rank(text: str) -> str | None:
    """順位の表現を比較できる形にそろえる。"""
    if re.search(r"準優勝", text):
        return "準優勝"
    if re.search(r"優勝", text):
        return "優勝"
    m = re.search(r"ベスト\s*([0-9０-９]+)", text)
    if m:
        return f"ベスト{int(m.group(1).translate(str.maketrans('０-９', '0-9')) if False else m.group(1))}"
    m = re.search(r"第?\s*([0-9]+)\s*位", text)
    if m:
        return f"{m.group(1)}位"
    return None


def sport_key(text: str) -> set[str]:
    """競技をざっくり同定する。表記ゆれを吸収するため語の集合で持つ。"""
    words = re.findall(
        r"陸上|水泳|競泳|バレー|バスケ|サッカー|テニス|卓球|バドミントン|柔道|剣道|"
        r"弓道|なぎなた|ソフトボール|ハンドボール|ラグビー|体操|新体操|ダンス|"
        r"チア|空手|相撲|レスリング|フェンシング|ボート|カヌー|自転車|登山|"
        r"ワンダーフォーゲル|少林寺|アーチェリー|ホッケー|ラクロス|山岳", text)
    return set(words)


def main() -> None:
    if not (OFFICIAL.is_file() and SITES.is_file()):
        raise SystemExit("先に parse_kotairen_results.py と "
                         "extract_club_achievements_from_sites.py を実行してください。")

    official = list(csv.DictReader(open(OFFICIAL, encoding="utf-8")))
    sites = list(csv.DictReader(open(SITES, encoding="utf-8-sig")))

    # 連盟側を 学校番号→年度→(競技語, 大会, 順位) で引けるように
    by_school: dict[str, list[dict]] = {}
    for r in official:
        by_school.setdefault(r["school_number"], []).append(r)

    conflicts = []
    for s in sites:
        if s["flag"] != "OK":
            continue                      # 要確認はそもそも人が見る前提
        text = s["text"]
        skey = sport_key(s["club"] + text)
        srank = norm_rank(text)
        recs = by_school.get(s["school_number"], [])

        if OUT_OF_SCOPE.search(s["club"] + text):
            conflicts.append({**base(s), "type": "C 未検証",
                              "detail": "高体連の管轄外（高野連・高文連など）のため連盟記録では裏が取れない",
                              "official": ""})
            continue

        if s["year"] not in VERIFIABLE_YEARS:
            conflicts.append({**base(s), "type": "D 検証範囲外",
                              "detail": f"連盟の記録は令和5〜7年度ぶんしかなく、{s['year']}は突き合わせられない",
                              "official": ""})
            continue

        same_year = [r for r in recs if r["year"] == s["year"]]
        matched = [r for r in same_year if skey & sport_key(r["sport"] + r["event"])]
        # 順位の比較は同じ大会の格どうしでのみ行う。都大会3位と関東大会7位を
        # 並べても食い違いではない（別々の大会の話）
        same_meet = [r for r in matched if r["meet"].startswith(s["meet"][:2])]

        if same_meet and srank:
            oranks = {norm_rank(r["rank"]) for r in same_meet} - {None}
            if oranks and srank not in oranks:
                conflicts.append({
                    **base(s), "type": "A 順位の相違",
                    "detail": f"学校サイト「{srank}」／連盟の記録「{'・'.join(sorted(oranks))}」",
                    "official": "; ".join(f"{r['meet']}{r['sport']}{r['event']}{r['rank']}"
                                          for r in same_meet[:3])})
            continue

        if s["meet"] in ("関東大会", "全国大会") and not matched:
            lvl = [r for r in same_year if r["meet"].startswith(s["meet"][:2])]
            conflicts.append({
                **base(s), "type": "B 記録に不在",
                "detail": (f"学校サイトは{s['year']}の{s['meet']}を書いているが、"
                           f"連盟の同年度一覧に同校の該当競技が見当たらない"),
                "official": "; ".join(f"{r['meet']}{r['sport']}{r['rank']}"
                                      for r in lvl[:3]) or "（同年度の記録なし）"})

    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        fields = ["type", "school", "club", "year", "meet", "site_text", "detail",
                  "official", "source"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(conflicts)

    from collections import Counter
    print(f"要確認 {len(conflicts)}件 → {OUT}")
    for k, v in sorted(Counter(c["type"] for c in conflicts).items()):
        print(f"  {k}: {v}件")


def base(s: dict) -> dict:
    return {"school": s["school"], "club": s["club"], "year": s["year"],
            "meet": s["meet"], "site_text": s["text"], "source": s["source"]}


if __name__ == "__main__":
    main()
