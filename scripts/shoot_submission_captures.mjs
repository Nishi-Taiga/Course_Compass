#!/usr/bin/env node
/* 提出フォーム用の画面キャプチャ（1600×900・docs/submission/）を撮り直す。
 *
 * なぜ要るか
 *   画面を直すたびに提出資料の図が古くなる。実際 2026-08-23 の直しで
 *   タブ名（比べる→くらべる）・マップ（同心円→実地図）・くらべるシートの
 *   出し方（全画面→右のボードのタブ）が全部変わり、capture1・2 が
 *   「いまの画面」と一致しなくなった。手で撮ると条件も選んだ学校も
 *   そのつど変わるので、入力を固定して撮る。
 *
 * 撮る条件は既存キャプチャのボード表示と同じにしてある:
 *   出発 練馬駅 / 通学45分以内 / 換算内申54（5教科22＋実技16×2）・当日380点
 *   / 部活 吹奏楽 / 最優先 通学の近さ
 *
 * capture3（表紙）は画面ではなくスライドなので、ここでは撮らない。
 *
 * 使い方: node scripts/shoot_submission_captures.mjs
 */
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";

const FILE = pathToFileURL(resolve("prototype/index.html")).href;
const OUT = resolve("docs/submission");
const VIEWPORT = { width: 1600, height: 900 };   // 提出フォームの指定サイズ
const ANSWERS = ["練馬", "45分以内", "22", "16", "380", "吹奏楽をやりたい", "通学の近さ"];

/* 地図タイルはOSMから。環境によってはブラウザから直接出られないので、
   curl で取ってPlaywright側に差し込む（タイルが無いと地図が灰色の箱になる）。 */
const CACHE = resolve(tmpdir(), "course-compass-tiles");
mkdirSync(CACHE, { recursive: true });
const UA = "Mozilla/5.0 (compatible; CourseCompass-screenshot/1.0; +https://github.com/Nishi-Taiga/Course_Compass)";
function tile(url) {
  const key = `${CACHE}/${url.replace(/[^a-z0-9]/gi, "_")}`;
  if (!existsSync(key)) {
    try { execFileSync("curl", ["-sS", "--max-time", "20", "-A", UA, "-o", key, url]); }
    catch { return null; }
  }
  const buf = readFileSync(key);
  return buf.length ? buf : null;
}

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await browser.newContext({
  viewport: VIEWPORT,
  colorScheme: "light",     // 提出資料は明るいほうで揃える
  reducedMotion: "reduce",  // 打鍵ごとの演出待ちを飛ばす
});
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.route("**tile.openstreetmap.org/**", async (route) => {
  const buf = tile(route.request().url());
  if (buf) await route.fulfill({ status: 200, contentType: "image/png", body: buf });
  else await route.abort();
});

await page.goto(FILE);
await page.click("#startBtn");
for (const t of ANSWERS) {
  await page.fill("#input", t);
  await page.press("#input", "Enter");
  await page.waitForTimeout(450);
}
await page.waitForTimeout(1000);

const cards = await page.locator(".card").count();
if (cards === 0) throw new Error("学校カードが1枚も出ていない");

// --- capture1: 対話と提案（3つの圏・マップ） ---
/* ⚠️ 会話は最後まで自動スクロールされているので、そのまま撮ると
      いちばん上の安全圏のカードが切れる。かといって先頭まで戻すと
      挨拶の往復だけになりカードが1枚も入らない。1枚目のカードが
      画面の上に来る位置に合わせ、直前のやりとりが少し覗く形にする
      （この図の見せどころは「対話」と「3つの圏」が同時に見えること）。 */
const toFirstCard = () => page.evaluate(() => {
  const chat = document.getElementById("chat");
  const card = document.querySelector("#chat .card");
  if (card) chat.scrollTop = card.offsetTop - chat.offsetTop - 56;
});
await toFirstCard();
await page.click("#tabMap");
await page.waitForTimeout(1200);
try { await page.waitForLoadState("networkidle", { timeout: 15000 }); } catch { /* タイルは無くても撮る */ }
const tiers = await page.locator(".card .tier").allInnerTexts();
if (new Set(tiers).size < 3) console.warn(`  ⚠️ 圏が3種そろっていない: ${tiers.join("・")}`);
await toFirstCard();
await page.waitForTimeout(200);
const visible = await page.locator("#chat .card").evaluateAll((cs) => {
  const box = document.getElementById("chat").getBoundingClientRect();
  return cs.filter((c) => { const r = c.getBoundingClientRect();
    return r.top >= box.top - 1 && r.bottom <= box.bottom + 1; }).length;
});
if (visible < 3) console.warn(`  ⚠️ 画面に収まったカードが${visible}枚（3枚以上が望ましい）`);
await page.screenshot({ path: `${OUT}/capture1_kaiwa_teian.png` });
console.log(`  ✅ capture1_kaiwa_teian.png（提案${cards}校 / ${[...new Set(tiers)].join("・")}）`);

// --- capture2: くらべるシート（1枚地図・倍率5年推移） ---
const addable = page.locator(".card .cmp");
const n = Math.min(3, await addable.count());
for (let i = 0; i < n; i++) { await addable.nth(i).click(); await page.waitForTimeout(150); }
await page.click("#tabCmp");
await page.waitForTimeout(1500);
try { await page.waitForLoadState("networkidle", { timeout: 15000 }); } catch { /* 同上 */ }
if (await page.locator("#bbody .cmpsheet").count() !== 1) {
  throw new Error("くらべるシートがボードに出ていない");
}
const tiles = await page.locator(".amap img")
  .evaluateAll((els) => els.filter((e) => e.complete && e.naturalWidth > 0).length);
if (tiles === 0) console.warn("  ⚠️ 地図タイルが1枚も読めていない");
await page.screenshot({ path: `${OUT}/capture2_kuraberu_sheet.png` });
console.log(`  ✅ capture2_kuraberu_sheet.png（${n}校・タイル${tiles}枚）`);

if (errors.length) throw new Error(`JSの例外: ${errors[0]}`);
console.log("  ℹ️  capture3_hyoshi.png は表紙スライドなので撮り直し不要");
await browser.close();
