#!/usr/bin/env python3
"""正規化辞書のたたき台を作る（西さんの監修用）。

    python3 scripts/build_club_normalize_list.py

出力:
    data/seed/club_normalize.csv        機械的に寄せた案（raw_name → normalized + gender）
    data/seed/club_normalize_review.md  判断が要るものだけを抜き出した確認用

## 分担

仕様書は「正規化辞書は西が**監修**」としている。作成ではなく確認を頼む書き方なので、
機械的に決まるところはここで寄せ、**判断が割れるものだけ**を review.md に出す。
西さんが見るのは十数件で済む。

## 機械的に寄せるもの（判断不要）

  - 接尾辞      サッカー部 / サッカー同好会 / サッカー班 / サッカー → サッカー
  - 全角半角    ﾊﾞｽｹｯﾄﾎﾞｰﾙ → バスケットボール（NFKC）
  - 分かち書き  「卓 球」「水 泳」→ 卓球・水泳（装飾の空白）
  - 括弧書き    演劇(同好会) → 演劇
  - 男女        男子バスケットボール部 / バスケットボール部(女) →
                normalized=バスケットボール ＋ gender=男子/女子

⚠️ normalized を埋めても raw_name は書き換えない。サイト上の表記は残す
   （元表記に戻せなくなるため。仕様書§6.2の方針）。

## 判断が要るもの（review.md に出す）

  - 同好会・班を部と同列に検索へ出すか
  - 似ているが別物のペアを取り違えていないか（硬式テニス／ソフトテニス 等）
  - 略称と正式名（ESS／英語部 など）
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLUBS_CSV = ROOT / "data" / "seed" / "school_clubs.csv"
OUT_CSV = ROOT / "data" / "seed" / "club_normalize.csv"
OUT_MD = ROOT / "data" / "seed" / "club_normalize_review.md"

SUFFIX_RE = re.compile(r"(部|班|同好会|愛好会|クラブ|同好会|会)$")
BRACKET_RE = re.compile(r"[（(][^）)]*[）)]")

# 似ているが別物。まとめてはいけない組。取り違えると検索結果が嘘になる。
# 男女はここに入れない。名前ではなく gender 列で分ける（下の normalize 参照）。
DISTINCT_PAIRS = [
    ("硬式テニス", "ソフトテニス"),
    ("硬式野球", "軟式野球"),
]

# 同じものを指している可能性が高い略称・別名。西さんの確認待ち。
ALIAS_CANDIDATES = [
    ("ESS", "英語"),
    ("軽音", "軽音楽"),
    ("コンピュータ", "情報処理"),
    ("吹奏楽", "ウインドアンサンブル"),
    ("箏曲", "筝曲"),
]


GENDER_IN_BRACKET_RE = re.compile(r"[（(]([^）)]*)[）)]")

# 前置きの男女。1文字の「男」「女」は入れない —「女声合唱」の頭を落としてしまう。
# 括弧書きの「（男）」「（女）」は GENDER_IN_BRACKET_RE で別に拾う。
GENDER_PREFIX_RE = re.compile(r"^(男女|男子|女子)")
BRACKET_GENDER = {"男子": "男子", "男": "男子", "女子": "女子", "女": "女子",
                  "男女": "男女", "男・女": "男女"}


def normalize(name: str) -> tuple[str, str]:
    """機械的に決まるところだけ寄せて、(正規化名, 男女) を返す。

    ⚠️ 男女は名前から切り離し、別の欄で持つ（2026-08-23 西の指示で変更）。
       以前は「男子バスケットボール」「女子バスケットボール」という別々の語に
       していたが、そうすると「バスケがしたい」に2語が当たり、画面上は
       同じ部が2件に見える。名前は「バスケットボール」1語にして、
       男子/女子は gender 列（DBは school_clubs.gender）に逃がす。

    ⚠️ 括弧の中の男女も捨てない。「サッカー部（男子）」を「サッカー」だけに
       すると、同じ学校の男女が1つに潰れて数が合わなくなる。
    """
    s = unicodedata.normalize("NFKC", name)

    gender = ""
    for inner in GENDER_IN_BRACKET_RE.findall(s):
        flat = re.sub(r"[\s　]", "", inner)
        if flat in BRACKET_GENDER:
            gender = BRACKET_GENDER[flat]

    s = BRACKET_RE.sub("", s)                 # 演劇(同好会) → 演劇
    s = re.sub(r"[\s　・]", "", s)             # 「卓 球」→ 卓球
    for _ in range(2):                        # 「〜部会」のように2つ付く形がある
        s = SUFFIX_RE.sub("", s)
    s = s.strip()

    m = GENDER_PREFIX_RE.match(s)
    if m and s[m.end():]:                     # 「男子」だけの名前は種目が無いので触らない
        gender = m.group(1) if m.group(1) != "男女" else "男女"
        s = s[m.end():]
    return s, gender


def org_type(name: str) -> str:
    """部・同好会・班のどれか。normalized とは別に持つ（検索の出し分けに使う）。"""
    for word in ("同好会", "愛好会", "班", "クラブ", "部"):
        if name.endswith(word):
            return word
    return ""


def main() -> None:
    rows = list(csv.DictReader(CLUBS_CSV.open(encoding="utf-8-sig")))

    # raw_name ごとに、出現した学校を数える
    schools_of: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        schools_of[r["raw_name"]].add(r["school_name"])

    # キーは (正規化名, 男女)。男女は名前に混ぜず、別の列で持つ
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for raw in schools_of:
        groups[normalize(raw)].append(raw)

    # --- 案のCSV ---
    out = []
    for (norm, gender), raws in sorted(groups.items(), key=lambda kv: -sum(len(schools_of[r]) for r in kv[1])):
        for raw in sorted(raws, key=lambda r: -len(schools_of[r])):
            out.append({
                "raw_name": raw,
                "normalized": norm,
                "gender": gender,
                "org_type": org_type(raw),
                "schools": len(schools_of[raw]),
                "variants_in_group": len(raws),
                "decided_by": "auto",     # 西さんが直したら nishi に変える
            })
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # --- 判断が要るものだけ抜き出す ---
    gender_pairs = sorted({n for n, g in groups if (n, "男子") in groups and (n, "女子") in groups})

    org_mixed = []
    for (norm, _g), raws in groups.items():
        kinds = {org_type(r) for r in raws} - {""}
        if len(kinds) > 1:
            org_mixed.append((norm, sorted(raws, key=lambda r: -len(schools_of[r]))))
    org_mixed.sort(key=lambda kv: -sum(len(schools_of[r]) for r in kv[1]))

    all_names = {n for n, _g in groups}
    aliases = [(a, b) for a, b in ALIAS_CANDIDATES
               if any(a in n for n in all_names) and any(b in n for n in all_names)]

    # 略称らしい組を自動で拾う（「バスケ」は「バスケットボール」の先頭）
    names = sorted(all_names)
    weight = {n: sum(len(schools_of[r]) for g in ("", "男子", "女子", "男女")
                     for r in groups.get((n, g), [])) for n in names}
    abbrev = []
    for short in names:
        if len(short) < 3:
            continue
        longer = [n for n in names if n != short and n.startswith(short)]
        if longer:
            abbrev.append((short, longer[:3]))
    # 学校数の多い順。五十音順のままだと、よく使われる略称が下に埋もれる
    abbrev.sort(key=lambda kv: -(weight[kv[0]] + sum(weight[n] for n in kv[1])))

    # 1文字違いの組（サイト側の誤記の疑い。「バトミントン」など）
    def close(a: str, b: str) -> bool:
        if abs(len(a) - len(b)) > 1 or len(a) < 4:
            return False
        diff = sum(1 for x, y in zip(a, b) if x != y)
        return len(a) == len(b) and diff == 1
    typos = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not close(a, b):
                continue
            typos.append((a, b))
    typos.sort(key=lambda kv: -(weight[kv[0]] + weight[kv[1]]))

    lines = [
        "# 部活名の正規化 — 監修のお願い",
        "",
        f"自動生成: `scripts/build_club_normalize_list.py`（元データ {len(rows):,}件 / "
        f"異なり表記 {len(schools_of)}種 / 正規化後 {len(groups)}語）",
        "",
        "機械的に決まるところは `data/seed/club_normalize.csv` に寄せてあります。",
        "**判断が割れるものだけ**をここに出しました。ここだけ見ていただければ大丈夫です。",
        "",
        "決めていただいたら `club_normalize.csv` の `normalized` を直して、",
        "`decided_by` を `nishi` に変えてください。",
        "",
        "---",
        "",
        "## 1. 男女別の扱い（決定済み・確認のみ）",
        "",
        "種目名と男女は**別の欄**にしています（`normalized` と `gender`）。",
        "「バスケがしたい」には種目名1語で当たり、画面には",
        "「バスケットボール部（男子・女子）」のように男女を添えて出します。",
        "",
        "男子・女子の両方がある種目:",
        "",
    ]
    lines += [f"- {n}（男子・女子ともに存在）" for n in gender_pairs]
    lines += [
        "",
        "---",
        "",
        "## 2. 同好会・班を部と同列に検索へ出しますか",
        "",
        "同じ活動が学校によって「部」「同好会」「班」で呼び分けられています。",
        "（小山台は部活動全体を伝統的に「班」と呼びます）",
        "",
        "いまは normalized では同じ語に寄せ、`org_type` 列に種別を残しています。",
        "",
        "種別が混在している上位:",
        "",
    ]
    for norm, raws in org_mixed[:15]:
        lines.append(f"- **{norm}** … " + " / ".join(f"{r}（{len(schools_of[r])}校）" for r in raws))
    lines += [
        "",
        "---",
        "",
        "## 3. まとめてはいけない組（取り違えがないかの確認）",
        "",
        "似ていますが別物として扱っています。この判断で合っていますか。",
        "",
    ]
    for a, b in DISTINCT_PAIRS:
        lines.append(f"- {a} と {b}")
    lines += [
        "",
        "---",
        "",
        "## 4. 同じものを指していそうな別名",
        "",
        "寄せるべきか、別のままにすべきか判断をお願いします。",
        "",
    ]
    for a, b in aliases:
        ex_a = [n for n in names if a in n][:3]
        ex_b = [n for n in names if b in n][:3]
        lines.append(f"- **{a}** と **{b}** … 例: {'・'.join(ex_a)} / {'・'.join(ex_b)}")
    lines += [
        "",
        "### 略称と思われる組（自動検出）",
        "",
    ]
    for short, longer in abbrev[:15]:
        lines.append(f"- **{short}** … {'・'.join(longer)} と同じですか")
    lines += [
        "",
        "### 1文字違いの組（サイト側の誤記の疑い）",
        "",
    ]
    for a, b in typos[:15]:
        lines.append(f"- **{a}** と **{b}**")
    lines += [
        "",
        "---",
        "",
        "## 5. 1校にしか無い名前（独自の部）",
        "",
        "正規化の必要はありませんが、部活かどうかの判断が要るものが混ざっているかもしれません。",
        "",
    ]
    solo = sorted(
        [r for r, s in schools_of.items() if len(s) == 1],
        key=lambda r: r,
    )
    lines.append(f"{len(solo)}件あります。抜粋:")
    lines.append("")
    lines.append("　" + "、".join(solo[:60]))
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"{OUT_CSV.relative_to(ROOT)} -> {len(out)}行")
    print(f"{OUT_MD.relative_to(ROOT)} -> 監修用")
    print(f"  異なり表記 {len(schools_of)}種 → 正規化後 {len(all_names)}語"
          f"（男女つき {sum(1 for _n, g in groups if g)}組）")
    print(f"  男女ペアのある種目 {len(gender_pairs)}件")
    print(f"  部/同好会/班が混在 {len(org_mixed)}語")
    print(f"  1校のみの名前 {len(solo)}件")


if __name__ == "__main__":
    main()
