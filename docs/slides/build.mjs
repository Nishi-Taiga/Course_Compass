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
rose(s, 11.6, 1.1, 2.7, C.brassSoft, 84);
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
s.addText("都立高校は189校あります。", { x: 0.7, y: 1.35, w: 12, h: 0.4,
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
s.addText("● ＝ 都立高校 1校", { x: FX, y: FY + NR * SP + 0.06, w: 3.0, h: 0.3,
  fontFace: F, fontSize: 11, color: C.faint, margin: 0 });
s.addText("塾に通っていないご家庭は、この189校から自分で絞ることになります。", {
  x: 0.7, y: 5.0, w: 12, h: 0.45, align: "center",
  fontFace: F, fontSize: 18, bold: true, color: C.ink, margin: 0 });
s.addText("「うちの子は、どこから見ればいいのか」", { x: 0.7, y: 5.7, w: 12, h: 0.7, align: "center",
  fontFace: F, fontSize: 30, bold: true, color: C.ink, margin: 0 });
s.addText("進路コンパスは、この最初の数校をお出しします。", { x: 0.7, y: 6.55, w: 12, h: 0.5, align: "center",
  fontFace: F, fontSize: 17, color: C.muted, margin: 0 });

/* ── 3. 使い方 ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "3つの質問に答えると、候補が出ます");
img(s, `${D}/n_chat.png`, 0.9, 1.55, 5.5, dims.n_chat);
[["1", "最寄り駅と、通える時間",
   "住所は聞きません。最寄り駅と、通える時間だけをうかがいます。"],
 ["2", "成績の目安",
   "内申は5教科と実技を分けてうかがい、1020点満点での見込みを計算します。\nまだ分からない場合は飛ばせます。"],
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
  x: 0.7, y: 1.45, w: 5.8, h: 0.4, fontFace: F, fontSize: 14, color: C.muted, margin: 0 });

const CX = 3.5, HALF = 2.8, SPAN = 150;
const px = (rel) => CX + (rel / SPAN) * HALF;
[[C.safe, "余裕をもって臨める", -SPAN, -60], [C.match, "いまの見込みで届く", -60, 60], [C.chal, "あと一歩", 60, SPAN]]
.forEach(([col, t, a, b]) => {
  s.addShape("rect", { x: px(a), y: 2.72, w: px(b) - px(a), h: 0.52, fill: { color: col }, line: { type: "none" } });
  s.addText(t, { x: px(a), y: 2.72, w: px(b) - px(a), h: 0.52, align: "center", valign: "middle",
    fontFace: F, fontSize: 12.5, bold: true, color: "FFFFFF", margin: 0 });
});
s.addText("実際に提案された4校", { x: 0.7, y: 1.98, w: 5.8, h: 0.28, fontFace: F, fontSize: 11, color: C.faint, margin: 0 });
[["練馬", -93, C.safe, 0], ["北園", 12, C.match, -0.42], ["竹早", 19, C.match, 0.42], ["西", 127, C.chal, 0]]
.forEach(([n, rel, col, dx]) => {
  s.addShape("ellipse", { x: px(rel) - 0.09, y: 2.44, w: 0.18, h: 0.18, fill: { color: col }, line: { color: "FFFFFF", width: 1.2 } });
  s.addText(n, { x: px(rel) - 0.6 + dx, y: 2.16, w: 1.2, h: 0.26, align: "center",
    fontFace: F, fontSize: 11.5, bold: true, color: C.ink, margin: 0 });
});
s.addShape("line", { x: CX, y: 2.38, w: 0, h: 1.0, line: { color: C.brass, width: 2, dashType: "dash" } });
s.addText("お子さんの見込み 793点", { x: CX - 1.5, y: 3.42, w: 3.0, h: 0.3, align: "center",
  fontFace: F, fontSize: 12.5, bold: true, color: C.brass, margin: 0 });
s.addText("← 合格の目安が低い　　　　　　　　　　　高い →", { x: 0.7, y: 3.74, w: 5.6, h: 0.28,
  align: "center", fontFace: F, fontSize: 10.5, color: C.faint, margin: 0 });
img(s, `${D}/d_board.png`, 6.55, 1.55, 3.95, dims.d_board);
img(s, `${D}/n_cards.png`, 11.35, 3.05, 2.55, dims.n_cards);
s.addText([
  { text: "1校には絞りません\n", options: { bold: true, fontSize: 17, color: C.ink } },
  { text: "どの学校が合うかは、お子さんとご家庭にしか分かりません。\n順位はつけずに、数校をそのままお出しします。", options: { fontSize: 14, color: C.muted } },
], { x: 0.7, y: 4.3, w: 5.8, h: 1.1, fontFace: F, margin: 0 });
s.addText([
  { text: "点数で判定できない学校も候補に残します\n", options: { bold: true, fontSize: 17, color: C.ink } },
  { text: "高専や定時制は入試の方式が違うため、判定はせず、\n「測り方が違う」と書いて表示しています。", options: { fontSize: 14, color: C.muted } },
], { x: 0.7, y: 5.6, w: 5.8, h: 1.1, fontFace: F, margin: 0 });

/* ── 5. くらべる ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.frame };
title(s, "気になった学校を1枚にまとめて印刷できます");
img(s, `${D}/d_sheet.png`, 0.7, 1.6, 3.55, dims.d_sheet);
img(s, `${D}/n_sheetmap.png`, 0.7, 5.35, 1.55, dims.n_sheetmap);
[["自宅の最寄駅からの位置関係",
  "気になる学校を同じ縮尺の地図に並べます。自宅からどの方角に、どれだけ離れているかが分かります。"],
 ["部の実績・制服・倍率の5年推移",
  "公式記録から集めた部の実績、制服、倍率の推移を同じ紙に載せています。"],
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
s.addText("PDF・HTML・表など形式の違うデータを、1つの画面にまとめています。", {
  x: 0.7, y: 4.95, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, color: C.ink, margin: 0 });
s.addText("すべての表示に出典を付けています。学校の公式サイトや都の資料に、そのまま進めます。", {
  x: 0.7, y: 5.5, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, color: C.ink, margin: 0 });
s.addText("大会実績は部の実績として扱っています。生徒の氏名・学年・記録は、収集の時点で読み取っていません。", {
  x: 0.7, y: 6.05, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, color: C.ink, margin: 0 });
s.addText("出典を確認できたデータだけを使っています。", {
  x: 0.7, y: 6.65, w: 12, h: 0.45, fontFace: F, fontSize: 14.5, bold: true, color: C.brass, margin: 0 });

/* ── 7. チームと、これから ─────────────────────────── */
s = p.addSlide();
s.background = { color: C.navy };
rose(s, 13.1, 7.3, 2.0, C.brassSoft, 90);
s.addText("チームと、これから", { x: 0.7, y: 0.5, w: 12, h: 0.85, fontFace: F, fontSize: 32, bold: true, color: C.heroInk, margin: 0 });
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
s.addText([
  { text: "つくり方　", options: { bold: true, color: C.heroInk } },
  { text: "デモは外部に依存しない単一のHTMLで、どの端末でも開けます。検索APIは Cloudflare Workers と D1 で動いています。\n通学時間は駅間のつながりから10.5万通りを事前に計算し、急行の運転に合わせて補正しています。自動テスト29項目で確認しています。", options: { color: "93A1B9" } },
], { x: 0.7, y: 3.95, w: 12, h: 0.9, fontFace: F, fontSize: 13, margin: 0 });
s.addText([
  { text: "続け方　", options: { bold: true, color: C.heroInk } },
  { text: "データの更新はスクリプトと GitHub Actions で自動化しているため、年1回の入試制度の改定にも少人数で対応できます。\n運用費は月数百円ほどです。今後は私立高校への対応、口コミや校風、やさしい日本語と多言語に取り組みます。", options: { color: "93A1B9" } },
], { x: 0.7, y: 5.0, w: 12, h: 0.9, fontFace: F, fontSize: 13, margin: 0 });
s.addText("都立高校を選ぶとき、最初に開いてもらえるものにしたいと考えています。", {
  x: 0.7, y: 6.4, w: 12, h: 0.6, fontFace: F, fontSize: 19, bold: true, color: C.brassSoft, margin: 0 });

await p.writeFile({ fileName: `${D}/shinro-compass-slides.pptx` });
console.log("written");
