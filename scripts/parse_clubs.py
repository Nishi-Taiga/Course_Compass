#!/usr/bin/env python3
"""取得済みHTMLから部活リストを構造で抜き出す（LLMを使わない抽出器）。

Workers AI の招待が来なくても Step6 を終わらせるために書いた。
LLM版（extract_school_clubs.py --engine llm）と同じCSVを出すので、
招待が通ったら差し替えて精度を比べられる。

## なぜ構造で抜けるのか

当初は「学校ごとにHTMLがバラバラで決め打ちパーサーは書けない」と判断していたが、
これは3校試行時点の見立てだった。167校ぶんを取得して数え直すと、大半が
都立学校共通CMSの決まった形をしている。

    ul.club_ul の <li>          109校
    activities/club_N へのリンク  46校
    表・箇条書きなど個別          12校

構造で拾えると、キーワード辞書に載っていない部も取れる。芝商業の「ひがた部」
「いけだ部」、神津の「神津高チャレンジ同好会」のような独自の部は、
「部活らしい名前か」で判定すると落ちるが、一覧の項目として拾えば落ちない。
正解リスト（school_clubs_expected.md）が、まさにそこを試すために作られている。

⚠️ 表記ゆれ（サッカー部 / サッカー / 足球部）はここで正規化しない。
   サイト上の表記そのままを raw_name に入れる。正規化辞書は西が監修し、
   後段で normalized に埋める。ここで潰すと元表記に戻せなくなる。

⚠️ 部活は「有無のリスト」まで。盛んかどうかはここでは持たない（仕様書§6.2）。
   大会成績は別系統（school_club_achievements.csv）で集めている。
"""

from __future__ import annotations

import re

# --------------------------------------------------------------- 下ごしらえ

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[\s　\xa0]+")


def decode_html(body: bytes) -> str:
    """HTMLを文字列にする。文字コードは meta の charset を見てから決める。

    五日市の部活ページだけ Shift_JIS で、utf-8 決め打ちだと全部が文字化けする。
    """
    m = re.search(rb"""charset=["']?([A-Za-z0-9_\-]+)""", body[:2000])
    candidates = [m.group(1).decode("ascii", "ignore")] if m else []
    for enc in candidates + ["utf-8", "cp932", "euc-jp"]:
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def strip_noise(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    for tag in ("script", "style"):
        html = re.sub(rf"<{tag}\b.*?</{tag}>", "", html, flags=re.S | re.I)
    return html


def text_of(fragment: str) -> str:
    """タグを落として1行の文字列にする。"""
    s = fragment.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    s = TAG_RE.sub("", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return WS_RE.sub(" ", s).strip()


# 部活ではないものを落とす。見出しやナビが項目に混ざることがある。
#
# ⚠️ 部分一致で消してよい語だけをここに入れる。ナビの語（ホーム・トップ等）を
#    部分一致で消すと「ホームメイキング部」まで巻き添えになる。
#    それらは EXCLUDE_EXACT に入れて完全一致で落とす。
EXCLUDE_RE = re.compile(
    r"委員会|生徒会|部活動一覧|部活動について|活動方針|年間行事|お知らせ|"
    r"新着情報|一覧へ|詳しく|サイトマップ|問い合わせ|"
    r"募集要項|学校説明会|ダウンロード|"
    # 活動紹介の本文が項目に混ざる学校がある（国際の「活動日：月・水・土or日」
    # 「IH予選の大会報告！」「目黒区大会 春季大会 優勝」など）。部活名ではない
    r"活動日|練習日|活動場所|大会|優勝|入賞|予選|報告|参加|開催|結果|"
    r"[：:！!※]|"
    r"^\d+$|^令和|^平成|^\W+$"
)

EXCLUDE_EXACT = {
    "ホーム", "トップ", "ページ", "このページの先頭へ", "アクセス", "PDF", "pdf",
    "詳細", "一覧", "こちら", "次へ", "前へ", "メニュー", "検索", "部活動",
}

# 見出しがカテゴリかどうか
CATEGORY_RE = re.compile(r"運動部|文化部|学芸部|体育部|同好会|部活動|クラブ")


def _clean_item(raw: str) -> str | None:
    s = text_of(raw)
    if not s or len(s) > 30:
        return None
    if s in EXCLUDE_EXACT or EXCLUDE_RE.search(s):
        return None
    return s


def _headings_and(html: str, item_pattern: str) -> list[tuple[str, str]]:
    """見出しと項目を文書の順に走査して [(項目, 直近の見出し)] を返す。

    カテゴリ（運動部/文化部）は項目の直前の見出しから取る。見出しを別々に
    探して後で対応づけると、順序がずれた学校で category が入れ違う。
    """
    token = re.compile(
        r"<h([1-4])[^>]*>(?P<head>.*?)</h\1>|" + item_pattern,
        re.S | re.I,
    )
    out: list[tuple[str, str]] = []
    category = ""
    for m in token.finditer(html):
        head = m.groupdict().get("head")
        if head is not None:
            t = text_of(head)
            # 「部活動」だけの見出しはカテゴリではなくページ見出しなので採らない
            category = t if CATEGORY_RE.search(t) and t not in ("部活動", "部活動・生徒会") else category
            continue
        item = m.groupdict().get("item")
        if item is None:
            continue
        name = _clean_item(item)
        if name:
            out.append((name, category))
    return out


# ------------------------------------------------------------- 3つの取り方

def _from_club_ul(html: str) -> list[tuple[str, str]]:
    """① 共通CMSの ul.club_ul（109校）。いちばん確実。"""
    found: list[tuple[str, str]] = []
    category = ""
    token = re.compile(
        r"<h([1-4])[^>]*>(?P<head>.*?)</h\1>"
        r"|<ul[^>]*class=\"[^\"]*club_ul[^\"]*\"[^>]*>(?P<ul>.*?)</ul>",
        re.S | re.I,
    )
    for m in token.finditer(html):
        if m.groupdict().get("head") is not None:
            t = text_of(m.group("head"))
            category = t if CATEGORY_RE.search(t) and t not in ("部活動", "部活動・生徒会") else category
            continue
        for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group("ul"), re.S | re.I):
            name = _clean_item(li)
            if name:
                found.append((name, category))
    return found


# 小山台は部活動を伝統的に「班活動」と呼び、各部が「〜班」で並んでいる。
# 「部」だけを見ていると、この学校だけ0件になる。
CLUBLIKE_RE = re.compile(r"(部|班|同好会|クラブ|愛好会)$")

"""カテゴリの見出し。部活名としては採らない（「運動部」も末尾が「部」のため）。"""
CATEGORY_WORDS = {
    "運動部", "文化部", "学芸部", "体育部", "同好会", "部活動", "部活動・生徒会",
    "運動系", "文化系", "運動部・文化部", "クラブ", "部活",
}


def _from_club_links(html: str) -> list[tuple[str, str]]:
    """② 部ごとの個別ブロック（46校）。

    2つの形がある。どちらも拾う。
      a) 個別ページへのリンクの文字列が部活名
      b) ブロックの見出し（h3/h4）が部活名。神津の天文部・神津高チャレンジ同好会、
         芝商業のひがた部・いけだ部がこの形で、一覧(club_ul)の下に置かれている
    """
    found = _headings_and(
        html,
        r"<a[^>]*href=\"[^\"]*activities/club_\d+[^\"]*\"[^>]*>(?P<item>[^<]*)</a>",
    )

    # b) 見出しそのものが部活名のケース
    category = ""
    for m in re.finditer(r"<h([1-4])[^>]*>(.*?)</h\1>", html, re.S | re.I):
        t = text_of(m.group(2))
        if not t or len(t) > 30:
            continue
        if t in CATEGORY_WORDS:
            category = t
            continue
        if CLUBLIKE_RE.search(t) and t not in EXCLUDE_EXACT and not EXCLUDE_RE.search(t):
            found.append((t, category))
    return found


def _from_generic(html: str) -> list[tuple[str, str]]:
    """③ 表や箇条書き（12校）。①②で取れなかった学校の受け皿。

    ここだけは「部活らしい名前か」で選ぶしかない。末尾が部/同好会等のものを拾う。
    独自の部（ひがた部など）も末尾が「部」なら拾えるが、
    「神津高チャレンジ同好会」のような形も含めて末尾で判定している。
    """
    # 箇条書き・表のセルに加えて、リンクや小さな箱も見る。
    # 八潮は <a> だけ、六郷工科は <div class="box-title">、
    # 広尾は <td><b><font>運　動　部</font></b></td> のように font/b の中に置いている。
    items = _headings_and(
        html,
        r"<(?:li|td|th|dd|a|div|p|font|span|b|strong)[^>]*>(?P<item>[^<]{1,30})"
        r"</(?:li|td|th|dd|a|div|p|font|span|b|strong)>",
    )

    # 広尾・五日市は部活一覧を表で組んでいて、カテゴリも見出しタグではなく
    # ただのセル（しかも「運 動 部」と分かち書き）。項目の並びを順に見て、
    # カテゴリらしいセルが出たらそこから下をそのカテゴリとして扱う。
    out: list[tuple[str, str]] = []
    current = ""
    for name, heading in items:
        flat = name.replace(" ", "")
        if flat in CATEGORY_WORDS:
            current = flat
            continue
        category = heading or current
        # 語尾が「部」等ならそれだけで採る。カテゴリの下にいるなら語尾は問わない
        # （「卓 球」「野 球」のように部を付けずに並べる学校があるため）
        if CLUBLIKE_RE.search(name):
            out.append((name, category))
        elif category and CATEGORY_RE.search(category) and len(flat) <= 12:
            out.append((name, category))

    # セル内に「サッカー部、野球部、…」と詰め込む学校がある
    if len(out) < 5:
        for name, category in items:
            for piece in re.split(r"[、,・／/\s]+", name):
                piece = piece.strip()
                if piece and len(piece) <= 20 and CLUBLIKE_RE.search(piece):
                    out.append((piece, category))
    return out


STRATEGIES = [
    ("club_ul", _from_club_ul),
    ("club_link", _from_club_links),
    ("generic", _from_generic),
]

DEDUPE_STRIP = re.compile(r"[()（）\s　・]|部$|班$|同好会$|クラブ$|愛好会$")


def dedupe_key(name: str) -> str:
    """同じ部の別表記を1つに寄せるための鍵。

    芝商業のように、同じ部を「一覧」と「個別ブロック」で二重に載せる学校がある。
    しかも表記が揃っていない（一覧は「バスケットボール(男子)」、個別は
    「男子バスケットボール部」）。語の並びまで違うので、文字を並べ替えて比べる。

    「男子バレーボール部」と「女子バレーボール部」は男/女が違うので別物のまま残る。
    """
    s = name
    for _ in range(2):                      # 「〜部（男子）」のように2回落ちる形がある
        s = DEDUPE_STRIP.sub("", s)
    return "".join(sorted(s))


def parse_clubs(html: str) -> tuple[list[dict], str]:
    """部活リストと、どの取り方で拾えたかを返す。

    ⚠️ ①と②は**両方**適用して足し合わせる。片方だけ採ってはいけない。
       神津は運動部・文化部を ul.club_ul で並べたうえで、天文部と
       神津高チャレンジ同好会だけ個別ブロック（activities/club_N）で
       下に置いている。片方で打ち切ると、この2部が落ちる。
       芝商業も同じ作りで、ひがた部・いけだ部・ワープロ部が個別ブロック側にある。

    ③は当てずっぽうが混じるので、①②で足りないときだけ使う。
    """
    html = strip_noise(html)

    collected: list[tuple[str, str]] = []
    used: list[str] = []
    for name, fn in STRATEGIES[:2]:
        try:
            found = fn(html)
        except Exception:
            found = []
        if found:
            collected.extend(found)
            used.append(name)

    if len({dedupe_key(n) for n, _ in collected}) < 5:
        try:
            extra = _from_generic(html)
            if extra:
                collected.extend(extra)
                used.append("generic")
        except Exception:
            pass

    merged: dict[str, tuple[str, str]] = {}
    for item, cat in collected:
        key = dedupe_key(item)
        if key not in merged:
            merged[key] = (item, cat)
            continue
        prev, prev_cat = merged[key]
        # 同じ部の別表記。「サッカー部」のように部が付く方を残す
        if CLUBLIKE_RE.search(item) and not CLUBLIKE_RE.search(prev):
            merged[key] = (item, prev_cat or cat)
        elif not prev_cat and cat:
            merged[key] = (prev, cat)

    return (
        [{"raw_name": n, "category": c} for n, c in merged.values()],
        "+".join(used) or "none",
    )
