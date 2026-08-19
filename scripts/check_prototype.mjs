#!/usr/bin/env node
/* プロトタイプ（prototype/index.html）を実際にブラウザで動かす通しテスト。
 *
 * 作った理由: PR #13 で比較ボタンを消したとき、スクリプト側の参照が残って
 * 例外になり、**学校カードが1枚も出ない**状態のまま気づかずマージした。
 * 画面は開くので「壊れて見えない」のがこの不具合の厄介なところで、
 * JSの例外とカードの枚数まで見ないと検知できない。
 *
 * 使い方: node scripts/check_prototype.mjs
 */
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const FILE = pathToFileURL(resolve("prototype/index.html")).href;
const results = [];
const check = (name, cond, detail = "") => {
  results.push({ name, ok: !!cond });
  console.log(`  ${cond ? "✅" : "❌"} ${name}${detail ? `  ${detail}` : ""}`);
};

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
// reducedMotion: 打鍵ごとの演出待ち（1手あたり0.6秒）を飛ばす。
// 画面のロジックは同じで、テストが待ち時間に左右されなくなる
const page = await browser.newPage({
  viewport: { width: 1100, height: 900 },
  reducedMotion: "reduce",
});

const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
// 地図タイルは外部（OSM）。テストで叩かない — 表示の有無はDOMで確かめる
await page.route("**://tile.openstreetmap.org/**", (r) => r.abort());

await page.goto(FILE);
await page.click("#startBtn");

console.log("── 対話 ──");
// 駅 → 通学時間 → 内申5教科 → 実技4教科 → 当日点 → 希望
for (const t of ["練馬", "40分以内", "22", "16", "380", "吹奏楽をやりたい"]) {
  await page.fill("#input", t);
  await page.press("#input", "Enter");
  await page.waitForTimeout(500);
}
await page.waitForTimeout(700);

const cards = await page.locator(".card").count();
check("学校カードが出る", cards > 0, `${cards}枚`);
check("JSの例外が出ていない", errors.length === 0, errors[0] ?? "");

console.log("\n── くらべるシート ──");
const addable = page.locator(".card .cmp");
const n = Math.min(3, await addable.count());
for (let i = 0; i < n; i++) await addable.nth(i).click();
check("シートに追加できる", n > 0, `${n}校`);

await page.evaluate(() => window.openSheet());
await page.waitForTimeout(600);

const sheet = page.locator("#sheetBody");
check("1枚地図が出る", (await sheet.locator(".ovmapwrap").count()) === 1);
// SVGの <text> は allInnerTexts() が空になるので textContent で読む
const ovLabels = await sheet.locator(".ovmapwrap svg text")
  .evaluateAll((els) => els.map((e) => e.textContent ?? ""));
check("1枚地図に自宅の最寄駅が出る", ovLabels.some((t) => t.includes("練馬")),
  ovLabels.filter((t) => t.includes("駅")).join(" "));
check("1枚地図に学校が全部載る",
  (await sheet.locator(".ovkey span").count()) === n, `${await sheet.locator(".ovkey span").count()} / ${n}`);

const access = sheet.locator(".maptbl .amap");
check("学校ごとの地図が出る", (await access.count()) === n, `${await access.count()} / ${n}`);
const badges = await sheet.locator(".maptbl .mbadge").allInnerTexts();
check("学校ごとの地図が自宅の最寄駅を起点にしている",
  badges.every((b) => b.includes("練馬駅から")), badges[0]?.replace(/\n/g, " / ") ?? "");
check("最後の徒歩・バス区間も残っている",
  badges.every((b) => /徒歩|バス/.test(b)));
check("シートでJSの例外が出ていない", errors.length === 0, errors[0] ?? "");

console.log("\n── ものづくり志望と高専 ──");
await page.evaluate(() => window.closeSheet());
const page2 = await browser.newPage({ viewport: { width: 1100, height: 900 }, reducedMotion: "reduce" });
page2.on("pageerror", (e) => errors.push(String(e)));
await page2.route("**://tile.openstreetmap.org/**", (r) => r.abort());
await page2.goto(FILE);
await page2.click("#startBtn");
for (const t of ["品川シーサイド", "40分以内", "20", "14", "330", "ものづくりをやりたい"]) {
  await page2.fill("#input", t);
  await page2.press("#input", "Enter");
  await page2.waitForTimeout(400);
}
await page2.waitForTimeout(600);
const names2 = await page2.locator(".card h3").allInnerTexts();
check("ものづくり志望で高専が候補に出る", names2.some((n) => n.includes("高専")), names2.join("・"));
check("高専に合格の目安点を出していない",
  !(await page2.locator(".card:has-text('高専') .fact").allInnerTexts()).some((t) => /目安を準備中|\d+点/.test(t)));

// 何も言わなければ高専は出さない（既定は全日制のまま）
const page3 = await browser.newPage({ viewport: { width: 1100, height: 900 }, reducedMotion: "reduce" });
page3.on("pageerror", (e) => errors.push(String(e)));
await page3.route("**://tile.openstreetmap.org/**", (r) => r.abort());
await page3.goto(FILE);
await page3.click("#startBtn");
for (const t of ["品川シーサイド", "40分以内", "20", "14", "330", "部活をがんばりたい"]) {
  await page3.fill("#input", t);
  await page3.press("#input", "Enter");
  await page3.waitForTimeout(400);
}
await page3.waitForTimeout(600);
const names3 = await page3.locator(".card h3").allInnerTexts();
check("希望がなければ高専は出さない", !names3.some((n) => n.includes("高専")), names3.join("・"));

await browser.close();
const ng = results.filter((r) => !r.ok);
console.log(`\n${results.length - ng.length} / ${results.length} 件 通過`);
if (ng.length) { console.log("失敗:"); ng.forEach((r) => console.log(`  - ${r.name}`)); process.exit(1); }
console.log("すべて通過しました。");
