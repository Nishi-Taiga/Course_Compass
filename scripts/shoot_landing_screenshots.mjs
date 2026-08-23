#!/usr/bin/env node
/* ランディングページ（index.html）の「使い方」に載せる、くらべるシートの
 * デスクトップ表示／モバイル表示のスクリーンショットを撮り直す。
 *
 * 手で撮ると対話の答え方や追加した学校がそのつど変わってしまい、
 * 撮り直すたびに載っている学校が入れ替わる。check_prototype.mjs と同じ
 * 入力（練馬 / 40分以内 / 22 / 16 / 380 / 吹奏楽）で毎回同じ3校を出す。
 *
 * 使い方: node scripts/shoot_landing_screenshots.mjs
 * 出力  : assets/landing/cmp-desktop.jpg, assets/landing/cmp-mobile.jpg
 */
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";

const FILE = pathToFileURL(resolve("prototype/index.html")).href;
const OUT = resolve("assets/landing");
mkdirSync(OUT, { recursive: true });

/* 地図タイルはOSMから取る。環境によってはブラウザから直接出られない
   （プロキシ配下など）ので、curl で取ってPlaywright側に差し込む。
   タイルが無いと位置関係の地図が灰色の箱になり、載せる意味が無くなる。 */
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

/* clipToMap=true のときは、位置関係の地図の下端で切る。ビューポートの高さを
   決め打ちにすると、行の高さが変わるたびに地図が途中で切れる。 */
async function shoot(name, viewport, deviceScaleFactor, clipToMap) {
  const ctx = await browser.newContext({
    viewport, deviceScaleFactor,
    colorScheme: "light",   // ページに載せる図は明るいほうで揃える
    reducedMotion: "reduce", // 打鍵ごとの演出待ちを飛ばす
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
  for (const t of ["練馬", "40分以内", "22", "16", "380", "吹奏楽をやりたい", "特にない"]) {
    await page.fill("#input", t);
    await page.press("#input", "Enter");
    await page.waitForTimeout(450);
  }
  await page.waitForTimeout(900);

  const addable = page.locator(".card .cmp");
  const n = Math.min(3, await addable.count());
  if (n === 0) throw new Error(`${name}: 学校カードが1枚も出ていない`);
  for (let i = 0; i < n; i++) { await addable.nth(i).click(); await page.waitForTimeout(150); }

  await page.evaluate(() => window.openSheet());
  await page.waitForTimeout(1200);
  try { await page.waitForLoadState("networkidle", { timeout: 15000 }); } catch { /* タイルは無くても撮る */ }

  const tiles = await page.locator(".amap img")
    .evaluateAll((els) => els.filter((e) => e.complete && e.naturalWidth > 0).length);
  if (tiles === 0) console.warn(`  ⚠️ ${name}: 地図タイルが1枚も読めていない`);

  if (clipToMap) {
    const box = await page.locator("#ovmapslot .ovmapwrap").boundingBox();
    if (box) {
      await page.setViewportSize({ width: viewport.width, height: Math.ceil(box.y + box.height + 14) });
      await page.waitForTimeout(500);
    }
  }
  await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 86 });
  if (errors.length) throw new Error(`${name}: JSの例外 — ${errors[0]}`);
  console.log(`  ✅ ${name}.jpg  (${n}校・タイル${tiles}枚)`);
  await ctx.close();
}

await shoot("cmp-desktop", { width: 1280, height: 860 }, 2, true);
await shoot("cmp-mobile", { width: 390, height: 844 }, 2, false);
await browser.close();
