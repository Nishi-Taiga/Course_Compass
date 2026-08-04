#!/usr/bin/env python3
"""都立高入学者選抜 最終応募状況PDF → 行データ抽出の試作。

対象: data/fetched/ratio_{年}_{02,03,04}.pdf（01は総括表なのでスキップ）
出力: data/seed/ratios_{年}.csv (school, department, capacity, applicants, ratio)

PDFは2段組がテキスト抽出で1本の流れになるため、
「(漢字等の名前トークン列) 定員 応募数 倍率」の繰り返しを正規表現で拾う。
学校名は1文字ずつ空白が入る（例: 日 比 谷）ので連結する。
区市名は先頭に付くことがあるため既知リストで除去する。
"""
import csv
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

BASE = Path(__file__).resolve().parent.parent
WARDS = [
    "千代田", "中央", "港", "新宿", "文京", "台東", "墨田", "江東", "品川",
    "目黒", "大田", "世田谷", "渋谷", "中野", "杉並", "豊島", "北", "荒川",
    "板橋", "練馬", "足立", "葛飾", "江戸川", "八王子", "立川", "武蔵野",
    "三鷹", "青梅", "府中", "昭島", "調布", "町田", "小金井", "小平", "日野",
    "東村山", "国分寺", "国立", "福生", "狛江", "東大和", "清瀬", "東久留米",
    "武蔵村山", "多摩", "稲城", "羽村", "あきる野", "西東京", "西多摩",
    "瑞穂", "日の出", "檜原", "奥多摩",
    "大島", "八丈", "小笠原", "神津島", "新島", "三宅",
]


def load_school_names() -> list:
    """住所録CSVから正式な学校名リスト（長い順）を返す。"""
    import codecs
    path = BASE / "data" / "fetched" / "hs_address_csv.csv"
    names = []
    with codecs.open(path, encoding="cp932") as f:
        for row in csv.DictReader(f):
            n = row.get("学校名", "").strip()
            if n:
                names.append(n)
    return sorted(set(names), key=len, reverse=True)
# 「定員 応募 倍率」の3つ組。倍率は x.xx 形式
ROW = re.compile(r"([^\d]+?)\s*(\d{2,4})\s+(\d{1,4})\s+(\d{1,2}\.\d{2})")
# 男女別5列（定員 男 女 計 倍率）: R4・R5世代の一部
ROW5 = re.compile(r"([^\d]+?)\s*(\d{2,4})\s+(\d{1,4})\s+(\d{1,4})\s+(\d{1,4})\s+(\d{1,2}\.\d{2})")
# 男女別9列（定員男女計 応募男女計 倍率男女計）: R4・R5の普通科本表
ROW9 = re.compile(
    r"([^\d]+?)\s*(\d{1,4})\s+(\d{1,4})\s+(\d{2,4})\s+(\d{1,4})\s+(\d{1,4})\s+(\d{1,4})"
    r"\s+(\d{1,2}\.\d{2})\s+(\d{1,2}\.\d{2})\s+(\d{1,2}\.\d{2})")
HEADER_WORDS = ["募集人員", "最終応募人員", "最終応募倍率", "最終応募", "応募倍率",
                "応募状況", "校数", "最終", "男女計", "男女問わず"]
DEPT_HEAD = re.compile(r"\d?\s*[［\[]([^］\]]+)[］\]]")


def clean_name(raw: str, current_ward: list) -> str:
    """名前トークン列を連結・ヘッダ語除去して返す（区市名は剥がさない）。"""
    s = re.sub(r"\s+", " ", raw).strip()
    s = re.sub(r"[（(].*?[)）]", "", s)  # 注記括弧
    joined = "".join(s.split(" "))
    for h in HEADER_WORDS:
        joined = joined.replace(h, "")
    return joined


def match_school(joined: str, school_names):
    """校名候補を2通り（そのまま/区市名を剥がして）作って選ぶ。

    選定則: 残り文字列（=学科名のはず）が「別の校名で始まる」候補は
    区市名と校名の取り違え（例: 杉並農芸→(杉並,農芸…)）なので無効。
    有効候補のうち校名が最長のものを採用（例: 小平西 > 西）。
    タイなら区市名を剥がした側を優先（例: 杉並農芸→農芸）。
    """
    def try_prefix(s):
        for sn in school_names:  # 長い順
            if s.startswith(sn):
                return (sn, s[len(sn):])
        return None

    def rem_valid(rem):
        return rem == "" or try_prefix(rem) is None

    cands = []  # (school, rem, stripped?)
    for w in sorted(WARDS, key=len, reverse=True):
        if joined.startswith(w) and len(joined) > len(w):
            m2 = try_prefix(joined[len(w):])
            if m2:
                cands.append((*m2, True))
            break
    m = try_prefix(joined)
    if m:
        cands.append((*m, False))
    valid = [c for c in cands if rem_valid(c[1])] or cands
    if not valid:
        return None
    # 1) 残りゼロ（完全一致）が最優先→その中で最長校名（小平西>西）
    perfect = [c for c in valid if c[1] == ""]
    if perfect:
        best = max(perfect, key=lambda c: len(c[0]))
        return (best[0], best[1])
    # 2) 区市名を剥がした候補を優先（世田谷総合工科→総合工科）
    stripped = [c for c in valid if c[2]]
    if stripped:
        return (stripped[0][0], stripped[0][1])
    # 3) それ以外は最長校名
    best = max(valid, key=lambda c: len(c[0]))
    return (best[0], best[1])


def parse_pdf(path: Path, school_names):
    pdf = pdfium.PdfDocument(str(path))
    rows = []
    dept = ""
    last_school = ""
    first = pdf[0].get_textpage().get_text_range()
    if "総括表" in first[:200]:
        return rows  # 総括表ファイルはスキップ
    for page in pdf:
        text = page.get_textpage().get_text_range()
        text = text.replace("\r", " ").replace("\n", " ")
        gendered = re.search(r"男\s+女\s+計", text) is not None
        # 学科見出し（例: 1［普通科（ｺｰｽ、単位制以外の学校）］）を追跡
        pos = 0
        segments = []
        for m in DEPT_HEAD.finditer(text):
            segments.append((dept, text[pos:m.start()]))
            dept = m.group(1)
            pos = m.end()
        segments.append((dept, text[pos:]))
        ward = [""]
        for seg_dept, seg in segments:
            # 列形式が行単位で混在し得るため、情報量の多いパターンから順に
            # マッチさせ、既に使った範囲と重なるものは捨てる（レイヤ方式）
            taken = []
            found = []  # (start, name_raw, cap, app, ratio)
            layers = ([(ROW9, "9"), (ROW5, "5"), (ROW, "3")] if gendered
                      else [(ROW, "3")])
            for pat, kind in layers:
                for m in pat.finditer(seg):
                    span = (m.start(2), m.end(0))  # 数値部分の範囲で判定
                    if any(a < span[1] and span[0] < b for a, b in taken):
                        continue
                    taken.append(span)
                    if kind == "9":
                        vals = (int(m.group(4)), int(m.group(7)), float(m.group(10)))
                    elif kind == "5":
                        vals = (int(m.group(2)), int(m.group(5)), float(m.group(6)))
                    else:
                        vals = (int(m.group(2)), int(m.group(3)), float(m.group(4)))
                    found.append((m.start(0), m.group(1), *vals))
            for _, raw_name, cap, app, ratio in sorted(found):
                name = clean_name(raw_name, ward)
                if len(name) > 32 or re.fullmatch(r"[小合]?計", name):
                    continue
                if name.endswith("計") and name != "会計":
                    continue  # 「〜科計」等の小計行
                if "訂正" in name or "しました" in name:
                    continue
                if not (10 <= cap <= 600):
                    continue
                # 正式校名との照合で 校名/学科名 を分離
                mres = match_school(name, school_names)
                school, subdept = mres if mres else ("", name)
                if not school:
                    is_dept_word = bool(re.search(r"[\uff61-\uff9f]", name)) or "・" in name
                    if name and last_school and (len(name) <= 8 or is_dept_word):
                        # 校名列が空の継続行（同一校の別学科）
                        school, subdept = last_school, name
                    elif not name:
                        # 名前なし＝学校別小計・部門合計行（農業413=99+92+84+63+75で検算済）
                        continue
                    else:
                        school, subdept = name, ""
                if school:
                    last_school = school
                rows.append((school, seg_dept, subdept, cap, app, ratio))
    return rows


def main():
    years = sys.argv[1:] or ["r8"]
    for y in years:
        allrows = []
        school_names = load_school_names()
        for part in ("01", "02", "03", "04"):
            p = BASE / "data" / "fetched" / f"ratio_{y}_{part}.pdf"
            if p.exists():
                allrows += parse_pdf(p, school_names)
        out = BASE / "data" / "seed" / f"ratios_{y}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["school", "department", "sub_department", "capacity", "applicants", "ratio"])
            w.writerows(allrows)
        print(f"{y}: {len(allrows)} rows -> {out.name}")
        for r in allrows[:5]:
            print("  ", r)


if __name__ == "__main__":
    main()
