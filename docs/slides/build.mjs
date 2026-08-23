import pptxgen from "pptxgenjs";
import { imageSizeFromFile } from "image-size/fromFile";
const D = "/tmp/claude-0/-home-user-knowledge-base/ce7faca9-342a-5cd4-886e-c73f2ae459cd/scratchpad/deck";

/* 語り口について（2026-08-23 西の指摘で全面改稿）
   前の版は広告コピーの口調だった。次の3つをやめている。
     ・各ページの下に金色の「キメの一行」を置く仕掛け
     ・「〜ではなく、〜です」の反転構文（4ページで繰り返していた）
     ・「〜という設計です」「守ったルールです」と自分の仕事を自分で価値づける言い方
   あわせて「入り口」の連呼もやめた。やっていることをそのまま書く。 */

const C = {
  navy: "0B101C", heroInk: "F2F5FA", frame: "FBFCFE", surface: "F1F4F9",
  line: "D7DDE8", ink: "1A2333", muted: "5C6B84", faint: "8B97AC",
  accent: "33527E", brass: "A87F2F", brassSoft: "C9A85C",
  safe: "2E7D32", match: "0D47A1", chal: "C45000",
};
const F = "Yu Gothic";
const W = 13.33;

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";
p.author = "Team WINS";
p.title = "進路コンパス";

function rose(s, cx, cy, r, color, tp) {
  for (const k of [1, 0.72, 0.5])
    s.addShape("ellipse", { x: cx - r * k, y: cy - r * k, w: r * k * 2, h: r * k * 2,
      fill: { color: C.navy, transparency: 100 }, line: { color, width: 1, transparency: tp } });
}
function img(s, path, x, y, hIn, dim) {
  s.addImage({ path, x, y, w: hIn * dim.width / dim.height, h: hIn,
    shadow: { type: "outer", color: "1A2333", blur: 12, offset: 4, angle: 90, opacity: 0.35 } });
}
function title(s, t) {
  s.addText(t, { x: 0.7, y: 0.5, w: 12, h: 0.85, fontFace: F, fontSize: 32, bold: true, color: C.ink, margin: 0 });
}
const dims = {};
for (const n of ["n_chat", "n_cards", "n_sheetmap", "d_board", "d_sheet"])
  dims[n] = await imageSizeFromFile(`${D}/${n}.png`);

/* ── 1. 表紙 ─────────────────────────── */
let s = p.addSlide();
s.background = { color: C.navy };
rose(s, 11.6, 1.1, 2.7, C.brassSoft, 90);
rose(s, 1.4, 6.8, 1.9, C.brassSoft, 88);
s.addShape("ellipse", { x: W / 2 - 0.42, y: 1.30, w: 0.84, h: 0.84,
  fill: { color: C.navy, transparency: 100 }, line: { color: C.brassSoft, width: 2 } });
s.addText("N", { x: W / 2 - 0.42, y: 1.30, w: 0.84, h: 0.84, align: "center", valign: "middle",
  fontFace: F, fontSize: 20, bold: true, color: C.brassSoft, margin: 0 });
s.addText("進路コンパス", { x: 0, y: 2.45, w: W, h: 1.15, align: "center",
  fontFace: F, fontSize: 54, bold: true, color: C.heroInk, margin: 0 });
s.addText("会話で、都立高校の候補を見つけます。", { x: 0, y: 3.72, w: W, h: 0.6, align: "center",
  fontFace: F, fontSize: 23, color: C.brassSoft, margin: 0 });
s.addText("塾に通っていないご家庭でも使えます。", { x: 0, y: 4.44, w: W, h: 0.5, align: "center",
  fontFace: F, fontSize: 15, color: C.faint, margin: 0 });
s.addText([{ text: "Team WINS", options: { bold: true, color: C.heroInk } },
           { text: "   西 ・ 寒河江 ・ 安田", options: { color: C.faint } }],
  { x: 0, y: 6.15, w: W, h: 0.4, align: "center", fontFace: F, fontSize: 14, margin: 0 });
s.addText("都知事杯オープンデータ・ハッカソン2026 サービス開発部門", { x: 0, y: 6.6, w: W, h: 0.4,
  align: "center", fontFace: F, fontSize: 12, color: C.faint, margin: 0 });

/* ── 2. 課題 ─────────────────────────────────
   ⚠️ 前は189個の点を2面並べ、片方だけ4個に色をつけていたが、
      2%の差なので遠目には同じ絵に見え、「間違い探し」になっていた。
      1枚の絵にして、注釈で2通りの読み方を与える形に変えた。
      27×7＝189。点1つが1校であることも図の中に書く。 */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "どこから見ればいいか、分からない");
s.addText("都内では毎年およそ7.9万人が中学を卒業し、都立高校は189校あります。", { x: 0.7, y: 1.35, w: 12, h: 0.4,
  fontFace: F, fontSize: 17, color: C.muted, margin: 0 });

const NC = 27, NR = 7, SP = 0.26, DT = 0.13;
const FX = (13.33 - ((NC - 1) * SP + DT)) / 2, FY = 2.55;
// 絞られた数校（連続した4つ）。ばらけていると「選ばれた一群」に見えない
const PICK = { r: 3, c0: 12, n: 4 };
for (let r = 0; r < NR; r++) for (let c = 0; c < NC; c++) {
  const on = r === PICK.r && c >= PICK.c0 && c < PICK.c0 + PICK.n;
  const d = on ? 0.19 : DT;
  s.addShape("ellipse", { x: FX + c * SP - (d - DT) / 2, y: FY + r * SP - (d - DT) / 2, w: d, h: d,
    fill: { color: on ? C.brass : "B9C4D6" }, line: { type: "none" } });
}
// 絞られた数校を囲う
const bx = FX + PICK.c0 * SP - 0.09, by = FY + PICK.r * SP - 0.09;
s.addShape("roundRect", { x: bx, y: by, w: (PICK.n - 1) * SP + DT + 0.18, h: DT + 0.18, rectRadius: 0.06,
  fill: { type: "none" }, line: { color: C.brass, width: 1.8 } });
// 上からの引き出し
const cx = bx + ((PICK.n - 1) * SP + DT + 0.18) / 2;
s.addShape("line", { x: cx, y: 2.16, w: 0, h: by - 2.16, line: { color: C.brass, width: 1.2 } });
s.addText("塾に通うご家庭は、先生が「まずこの数校から」と絞ってくれます", {
  x: cx - 3.2, y: 1.84, w: 6.4, h: 0.32, align: "center",
  fontFace: F, fontSize: 14, bold: true, color: C.brass, margin: 0 });
s.addText("● ＝ 都立高校 1校", { x: 8.75, y: 1.44, w: 3.0, h: 0.3,
  fontFace: F, fontSize: 11.5, color: C.faint, margin: 0 });
// 出典は最下段へ。上に置くと本文と金の注記の間に割り込む
s.addText("卒業者数は東京都教育委員会「中学校卒業者の進路状況」令和7年度速報（78,627人）", {
  x: 0.7, y: 7.02, w: 11, h: 0.28, fontFace: F, fontSize: 9.5, color: C.faint, margin: 0 });
s.addText("塾に通っていないご家庭は、この189校から自分で絞ることになります。", {
  x: 0.7, y: 5.0, w: 12, h: 0.45, align: "center",
  fontFace: F, fontSize: 18, bold: true, color: C.ink, margin: 0 });
s.addText("「うちの子は、どこから見ればいいのか」", { x: 0.7, y: 5.62, w: 12, h: 0.6, align: "center",
  fontFace: F, fontSize: 23, color: C.muted, margin: 0 });
s.addText("進路コンパスは、この最初の数校をお出しします。", { x: 0.7, y: 6.35, w: 12, h: 0.55, align: "center",
  fontFace: F, fontSize: 21, bold: true, color: C.accent, margin: 0 });

/* ── 3. 使い方 ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "3つの質問に答えると、候補が出ます");
img(s, `${D}/n_chat.png`, 0.9, 1.55, 5.5, dims.n_chat);
[["1", "最寄り駅と、通える時間",
   "住所は聞きません。最寄り駅と、通える時間だけをうかがいます。"],
 ["2", "成績の目安",
   "内申と当日点の見込みをうかがい、1020点満点に換算します。\nまだ分からない場合は飛ばせます。"],
 ["3", "希望と、重視したいこと",
   "「吹奏楽をやりたい」「制服がない学校がいい」など、自由に入力できます。\n最後に、並べ方の基準を1つ選びます。"],
].forEach(([n, t, d], i) => {
  const y = 1.95 + i * 1.55;
  s.addShape("ellipse", { x: 4.7, y, w: 0.62, h: 0.62, fill: { color: C.accent }, line: { type: "none" } });
  s.addText(n, { x: 4.7, y, w: 0.62, h: 0.62, align: "center", valign: "middle",
    fontFace: F, fontSize: 22, bold: true, color: "FFFFFF", margin: 0 });
  s.addText(t, { x: 5.55, y: y - 0.04, w: 7.1, h: 0.5, fontFace: F, fontSize: 19, bold: true, color: C.ink, margin: 0 });
  s.addText(d, { x: 5.55, y: y + 0.46, w: 7.1, h: 0.9, fontFace: F, fontSize: 13.5, color: C.muted, margin: 0 });
});

/* ── 4. 提案の出し方 ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "余裕・ちょうど・あと一歩を混ぜて出します");
s.addText("お子さんの見込み点を基準に、3つに分けています。", {
  x: 0.7, y: 1.30, w: 5.8, h: 0.35, fontFace: F, fontSize: 14, color: C.muted, margin: 0 });

const CX = 3.5, HALF = 2.8, SPAN = 150;
const px = (rel) => CX + (rel / SPAN) * HALF;
const BY = 2.80, BH = 0.62;   // 帯の上端と高さ

s.addText("実際に提案された4校", { x: 0.7, y: 1.66, w: 5.8, h: 0.3,
  fontFace: F, fontSize: 11.5, bold: true, color: C.muted, margin: 0 });

/* ⚠️ 北園と竹早は点が0.13インチしか離れていないのに、ラベルは重なりを避けて
   左右0.42インチずらしてある。引き出し線を同じ高さで曲げると2本の横線が
   重なって1本の括弧に見え、どちらの点を指すのか結局読めない（8/23 2回目の
   レビューで指摘）。曲げる高さを1校ずつ変えて、線が交わらないようにする。 */
[["練馬", -93, C.safe, 0, 0], ["北園", 12, C.match, -0.42, 2.34],
 ["竹早", 19, C.match, 0.42, 2.44], ["西", 127, C.chal, 0, 0]]
.forEach(([n, rel, col, dx, elbow]) => {
  const mx = px(rel), lx = mx + dx;
  const LEAD = { color: C.faint, width: 0.75 };
  if (dx === 0) {
    s.addShape("line", { x: mx, y: 2.28, w: 0, h: 0.24, line: LEAD });
  } else {
    s.addShape("line", { x: lx, y: 2.28, w: 0, h: elbow - 2.28, line: LEAD });
    s.addShape("line", { x: Math.min(mx, lx), y: elbow, w: Math.abs(dx), h: 0, line: LEAD });
    s.addShape("line", { x: mx, y: elbow, w: 0, h: 2.52 - elbow, line: LEAD });
  }
  s.addShape("ellipse", { x: mx - 0.09, y: 2.52, w: 0.18, h: 0.18,
    fill: { color: col }, line: { color: "FFFFFF", width: 1.2 } });
  s.addText(n, { x: lx - 0.6, y: 2.02, w: 1.2, h: 0.26, align: "center",
    fontFace: F, fontSize: 11.5, bold: true, color: C.ink, margin: 0 });
});

/* 帯。見出しは短い語で、その下に意味を添える（見出しの3語と一致させる） */
[[C.safe, "余裕", "余裕をもって臨める", -SPAN, -60],
 [C.match, "ちょうど", "いまの見込みで届く", -60, 60],
 [C.chal, "あと一歩", "いまは少し足りない", 60, SPAN]]
.forEach(([col, short, long, a2, b2]) => {
  s.addShape("rect", { x: px(a2), y: BY, w: px(b2) - px(a2), h: BH,
    fill: { color: col }, line: { type: "none" } });
  s.addText([{ text: short + "\n", options: { fontSize: 13, bold: true } },
             { text: long, options: { fontSize: 9 } }],
    { x: px(a2), y: BY, w: px(b2) - px(a2), h: BH, align: "center", valign: "middle",
      fontFace: F, color: "FFFFFF", lineSpacingMultiple: 0.9, margin: 0 });
});

/* ⚠️ 「境目は60点」と書くだけでは図の上で確かめられない（2回目のレビューで指摘）。
   基準線と境目の目盛りを軸として置き、数字を図の中で読めるようにする。 */
s.addShape("line", { x: CX, y: 2.66, w: 0, h: BH + 0.28, line: { color: C.brass, width: 2, dashType: "dash" } });
[[-60, "−60点"], [60, "+60点"]].forEach(([rel, lab]) => {
  s.addShape("line", { x: px(rel), y: BY + BH, w: 0, h: 0.09, line: { color: C.muted, width: 1 } });
  s.addText(lab, { x: px(rel) - 0.5, y: BY + BH + 0.10, w: 1.0, h: 0.26, align: "center",
    fontFace: F, fontSize: 10, color: C.muted, margin: 0 });
});
s.addText("見込み 793点", { x: CX - 0.9, y: BY + BH + 0.36, w: 1.8, h: 0.28, align: "center",
  fontFace: F, fontSize: 12, bold: true, color: C.brass, margin: 0 });
s.addText("← 合格の目安が低い　　　　　　　　　　　高い →", { x: 0.7, y: BY + BH + 0.70, w: 5.6, h: 0.28,
  align: "center", fontFace: F, fontSize: 10.5, color: C.faint, margin: 0 });
img(s, `${D}/d_board.png`, 6.55, 1.55, 3.95, dims.d_board);
img(s, `${D}/n_cards.png`, 11.35, 3.05, 2.55, dims.n_cards);
/* ⚠️ ここは2段落・各3行あったが、割り当ての約20秒では読みきれず、
   声の届かない文字が画面に残っていた（8/23 プレゼン通しで発覚）。
   説明は1行に落とし、残りは口頭で足せる長さにしてある。 */
[["1校には絞りません",
  "順位はつけずに数校を並べます。どの学校が合うかは、ご家庭で判断していただくためです。"],
 ["高専・定時制も候補に残します",
  "入試の方式が違うため判定はせず、「測り方が違う」と書いて出します。"],
].forEach(([t, d], i) => {
  const y = 4.65 + i * 1.25;
  s.addText(t, { x: 0.7, y, w: 5.8, h: 0.4, fontFace: F, fontSize: 17, bold: true, color: C.ink, margin: 0 });
  s.addText(d, { x: 0.7, y: y + 0.42, w: 5.8, h: 0.4, fontFace: F, fontSize: 13.5, color: C.muted, margin: 0 });
});

/* ── 5. くらべる ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "気になった学校を1枚にまとめて印刷できます");
img(s, `${D}/d_sheet.png`, 0.7, 1.6, 3.55, dims.d_sheet);
img(s, `${D}/n_sheetmap.png`, 0.7, 5.35, 1.55, dims.n_sheetmap);
/* この1枚だけ説明が無く、上の地図が2回出ているように見えていた。
   最下端に置いたらフッター注記に見えたので、画像の右の空きに本文の重さで置く。 */
s.addText("スマートフォンでも\n同じものが見られます。", { x: 2.55, y: 5.75, w: 3.2, h: 0.6,
  fontFace: F, fontSize: 13, color: C.muted, margin: 0 });
/* ⚠️ 説明の順を、左の画像の並び（上=表 / 下=地図）に合わせてある。
   逆に並べると目線が上→下→上と往復する（8/23 レビューで指摘）。
   ⚠️ 3枚目で「住所は聞きません」と言っているので、ここも「自宅から」ではなく
   「最寄り駅から」で書く。表記は「最寄り駅」に統一。 */
[["部の実績・制服・倍率の5年推移",
  "公式記録から集めた部の実績、制服、倍率の推移を同じ紙に載せています。"],
 ["最寄り駅からの位置関係",
  "気になる学校を同じ縮尺の地図に並べます。最寄り駅からどの方角に、どれだけ離れているかが分かります。"],
 ["A4で印刷できます",
  "学校説明会や見学に持っていき、ご家族で見ながら話せます。"],
].forEach(([t, d], i) => {
  const y = 2.05 + i * 1.5;
  s.addShape("ellipse", { x: 6.05, y: y + 0.02, w: 0.16, h: 0.16, fill: { color: C.brass }, line: { type: "none" } });
  s.addText(t, { x: 6.4, y: y - 0.14, w: 6.3, h: 0.45, fontFace: F, fontSize: 17, bold: true, color: C.ink, margin: 0 });
  s.addText(d, { x: 6.4, y: y + 0.34, w: 6.3, h: 0.8, fontFace: F, fontSize: 13.5, color: C.muted, margin: 0 });
});

/* ── 6. データ ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "9つの公開データを組み合わせています");
[["学校一覧・学科", "東京都教育委員会"], ["応募倍率 R4〜R8", "東京都教育委員会"],
 ["中学校卒業者の進路状況", "東京都教育委員会"], ["進学指導重点校等の指定", "東京都教育委員会"],
 ["部活 約5,000件", "各校公式サイト"], ["制服", "各校公式サイト"],
 ["運動部の実績", "東京都高体連"], ["硬式野球・吹奏楽・美術", "都高野連・都吹連・国際美術展"],
 ["通学時間 10.5万通り", "station_database（CC BY-SA 4.0）"],
].forEach(([t, d], i) => {
  const x = 0.7 + (i % 3) * 4.1, y = 1.55 + Math.floor(i / 3) * 1.05;
  s.addShape("roundRect", { x, y, w: 3.75, h: 0.85, rectRadius: 0.08, fill: { color: "FFFFFF" }, line: { color: C.line, width: 1 } });
  s.addText(t, { x: x + 0.22, y: y + 0.08, w: 3.4, h: 0.4, fontFace: F, fontSize: 13.5, bold: true, color: C.ink, margin: 0 });
  s.addText(d, { x: x + 0.22, y: y + 0.45, w: 3.4, h: 0.35, fontFace: F, fontSize: 10.5, color: C.muted, margin: 0 });
});
s.addText("地図タイルは OpenStreetMap（ODbL）を使っています。", {
  x: 0.7, y: 4.62, w: 12, h: 0.3, fontFace: F, fontSize: 10.5, color: C.faint, margin: 0 });
s.addText("PDF・HTML・表など形式の違うデータを、1つの画面にまとめています。", {
  x: 0.7, y: 4.98, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, color: C.ink, margin: 0 });
s.addText("すべての表示に出典を付けています。学校の公式サイトや都の資料に、そのまま進めます。", {
  x: 0.7, y: 5.46, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, color: C.ink, margin: 0 });
/* ⚠️ 扱い方の2行は、2分のプレゼンでは口頭で拾えない（8/23 通しで発覚）。
   声が届かない前提で、目だけで拾えるよう囲って区別する。 */
s.addShape("roundRect", { x: 0.7, y: 5.95, w: 12, h: 1.0, rectRadius: 0.08,
  fill: { color: "FFFFFF" }, line: { color: C.brass, width: 1.4 } });
s.addText("出典を確認できたデータだけを使っています。", {
  x: 1.0, y: 6.06, w: 11.4, h: 0.4, fontFace: F, fontSize: 14.5, bold: true, color: C.brass, margin: 0 });
s.addText("大会実績は部の実績として扱っています。生徒の氏名・学年・記録は、収集の時点で読み取っていません。", {
  x: 1.0, y: 6.48, w: 11.4, h: 0.4, fontFace: F, fontSize: 13, color: C.muted, margin: 0 });

/* ── 7. チームと、これから ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.navy };
rose(s, 13.1, 7.3, 2.0, C.brassSoft, 90);
s.addText("チーム", { x: 0.7, y: 0.5, w: 12, h: 0.85, fontFace: F, fontSize: 32, bold: true, color: C.heroInk, margin: 0 });
[["西", "企画・データ整備", "塾で保護者と面談している立場から、\n必要な情報と伝え方を決めています。"],
 ["寒河江", "推薦ロジック・API", "区分の判定と並べ方、Cloudflare上の\n検索APIを担当しています。"],
 ["安田", "UI・画面設計", "保護者が迷わない画面と、\n印刷して使えるシートを設計しています。"],
].forEach(([n, r, d], i) => {
  const x = 0.7 + i * 4.1;
  s.addShape("roundRect", { x, y: 1.55, w: 3.75, h: 2.15, rectRadius: 0.12, fill: { color: "141B2A" }, line: { color: "2B3650", width: 1 } });
  s.addText(n, { x: x + 0.28, y: 1.75, w: 3.2, h: 0.45, fontFace: F, fontSize: 20, bold: true, color: C.heroInk, margin: 0 });
  s.addText(r, { x: x + 0.28, y: 2.22, w: 3.2, h: 0.35, fontFace: F, fontSize: 12.5, color: C.brassSoft, margin: 0 });
  s.addText(d, { x: x + 0.28, y: 2.65, w: 3.2, h: 0.9, fontFace: F, fontSize: 11.5, color: "93A1B9", margin: 0 });
});

/* 札の中身は読み上げない前提。目に飛び込む短さにしてある。
   ⚠️ 「デモは単一HTML」を先頭に置いたら、技術の話が制限の申告に読めると
   指摘された（8/23 2回目）。実体である検索基盤を先に出す。 */
function chips(sl, lab, items, y) {
  sl.addText(lab, { x: 0.7, y: y + 0.08, w: 1.35, h: 0.42, fontFace: F, fontSize: 14,
    bold: true, color: C.brassSoft, margin: 0 });
  let x = 2.1;
  for (const it of items) {
    // 全角と半角で字幅が倍違う。全角1・半角0.5で数える（12pt の全角は約0.167インチ）
    const em = [...it].reduce((acc, ch) => acc + (/[\x20-\x7E]/.test(ch) ? 0.5 : 1), 0);
    const w = 0.30 + em * 0.17;
    sl.addShape("roundRect", { x, y, w, h: 0.58, rectRadius: 0.1,
      fill: { color: "141B2A" }, line: { color: "2B3650", width: 1 } });
    sl.addText(it, { x, y, w, h: 0.58, align: "center", valign: "middle",
      fontFace: F, fontSize: 12, color: "C3CDDF", margin: 0 });
    x += w + 0.22;
  }
}
chips(s, "つくり方", ["検索は Cloudflare Workers + D1", "配布用デモは単一HTMLで完結",
                     "通学時間 10.5万通りを事前計算", "自動テスト 51項目"], 4.15);
chips(s, "続け方", ["データ更新は GitHub Actions で自動", "運用費 月数百円"], 5.15);
s.addText("年に一度の入試情報の更新を、少人数のまま回せる形にしてあります。", {
  x: 0.7, y: 6.15, w: 12, h: 0.4, fontFace: F, fontSize: 13, color: "93A1B9", margin: 0 });

/* ── 8. これから ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.navy };
/* 飾りは入れない。下段の囲みと最後の2行に線が重なる */
s.addText("これから", { x: 0.7, y: 0.5, w: 12, h: 0.85, fontFace: F, fontSize: 32, bold: true, color: C.heroInk, margin: 0 });
s.addText("いまは都立高校の189校だけを扱っています。ここから増やしていきます。", {
  x: 0.7, y: 1.32, w: 12, h: 0.4, fontFace: F, fontSize: 15, color: "93A1B9", margin: 0 });

[["扱う学校を増やす", C.brassSoft,
  [["私立高校を候補に加える", "都立と私立は併願で決めるものなので、都立だけでは選び終わりません。"],
   ["中高一貫校・高専の拡充", "入試の方式が違う学校も、測り方の違いを書いたうえで並べます。"]]],
 ["学校を知る手がかりを増やす", C.brassSoft,
  [["校風", "各校公式サイトの教育目標やスクールポリシーから拾います。判定には使わず、知る手がかりとして出します。"],
   ["進学・進路の実績", "卒業後の進路を、公表されている範囲で並べます。"]]],
 ["使える人を増やす", C.brassSoft,
  [["やさしい日本語と多言語", "日本語で情報を集めるのが難しいご家庭にも届くようにします。"],
   ["学校説明会・見学の情報", "候補が決まったあと、次に何をすればいいかまで案内します。"]]],
].forEach(([head, col, items], i) => {
  const x = 0.7 + i * 4.1;
  s.addShape("roundRect", { x, y: 1.95, w: 3.75, h: 3.15, rectRadius: 0.12,
    fill: { color: "141B2A" }, line: { color: "2B3650", width: 1 } });
  s.addText(head, { x: x + 0.28, y: 2.15, w: 3.2, h: 0.4, fontFace: F, fontSize: 15,
    bold: true, color: col, margin: 0 });
  items.forEach(([t, d], j) => {
    const y = 2.68 + j * 1.15;
    s.addText(t, { x: x + 0.28, y, w: 3.2, h: 0.3, fontFace: F, fontSize: 12.5,
      bold: true, color: C.heroInk, margin: 0 });
    s.addText(d, { x: x + 0.28, y: y + 0.32, w: 3.2, h: 0.78, fontFace: F, fontSize: 10.5,
      color: "93A1B9", margin: 0 });
  });
});

/* 増やさないものも書く。出典を出せないデータは載せない、が本PJの前提なので、
   拡張計画の中でそこだけ線を引いておく */
s.addShape("roundRect", { x: 0.7, y: 5.35, w: 12, h: 0.72, rectRadius: 0.1,
  fill: { color: "141B2A" }, line: { color: C.brass, width: 1.2 } });
s.addText([{ text: "増やさないもの　", options: { bold: true, color: C.brassSoft } },
           { text: "口コミは載せません。出典を出せないデータは、表示にも判定にも使いません。", options: { color: "C3CDDF" } }],
  { x: 1.0, y: 5.35, w: 11.4, h: 0.72, valign: "middle", fontFace: F, fontSize: 13, margin: 0 });

s.addText("保護者から利用料はいただきません。無料のまま続けられる形を、収益の側で用意しています。", {
  x: 0.7, y: 6.25, w: 12, h: 0.4, fontFace: F, fontSize: 13, color: "93A1B9", margin: 0 });
s.addText("塾に通っていないご家庭が、学校選びを始められる場所にしたいと考えています。", {
  x: 0.7, y: 6.68, w: 12, h: 0.45, fontFace: F, fontSize: 15, color: "C3CDDF", margin: 0 });

/* ページ番号。表紙とチーム紹介は濃い背景なので文字色を分ける */
p.slides.forEach((sl, i) => {
  const dark = i === 0 || i === p.slides.length - 1;
  sl.addText(String(i + 1), { x: 12.5, y: 6.95, w: 0.5, h: 0.3, align: "right",
    fontFace: F, fontSize: 10, color: dark ? "5C6B84" : C.faint, margin: 0 });
});

await p.writeFile({ fileName: `${D}/shinro-compass-slides.pptx` });
console.log("written");
