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
for (const t of ["練馬", "40分以内", "22", "16", "380", "吹奏楽をやりたい", "特にない"]) {
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

// 学校ごとの地図セクションは #28 で削除（1枚地図に集約）。ここでは
// 1枚地図が帰属表示（OSMクレジット）を持つことを確認する
check("1枚地図に帰属表示がある",
  (await sheet.locator(".ovmapwrap .mattr").count()) === 1);
check("シートでJSの例外が出ていない", errors.length === 0, errors[0] ?? "");

console.log("\n── ものづくり志望と高専 ──");
await page.evaluate(() => window.closeSheet());
const page2 = await browser.newPage({ viewport: { width: 1100, height: 900 }, reducedMotion: "reduce" });
page2.on("pageerror", (e) => errors.push(String(e)));
await page2.route("**://tile.openstreetmap.org/**", (r) => r.abort());
await page2.goto(FILE);
await page2.click("#startBtn");
for (const t of ["品川シーサイド", "40分以内", "20", "14", "330", "ものづくりをやりたい", "特にない"]) {
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
for (const t of ["品川シーサイド", "40分以内", "20", "14", "330", "部活をがんばりたい", "特にない"]) {
  await page3.fill("#input", t);
  await page3.press("#input", "Enter");
  await page3.waitForTimeout(400);
}
await page3.waitForTimeout(600);
const names3 = await page3.locator(".card h3").allInnerTexts();
check("希望がなければ高専は出さない", !names3.some((n) => n.includes("高専")), names3.join("・"));

/* ---- 2026-08-19 欠陥チェックで見つかった退行の再発防止 ---- */
console.log("\n── 希望の反映（部活・定時制・制服・複合） ──");
async function ask(inputs) {
  const pg = await browser.newPage({ viewport: { width: 1100, height: 900 }, reducedMotion: "reduce" });
  pg.on("pageerror", (e) => errors.push(String(e)));
  await pg.route("**://tile.openstreetmap.org/**", (r) => r.abort());
  await pg.goto(FILE);
  await pg.click("#startBtn");
  for (const t of inputs) {
    await pg.fill("#input", t);
    await pg.press("#input", "Enter");
    await pg.waitForTimeout(350);
  }
  await pg.waitForTimeout(600);
  const names = await pg.locator(".card h3").allInnerTexts();
  const state = await pg.evaluate(() => ({ wants: S.wants, limit: S.limit,
    ok: S.shown.every((c) => (!S.wants.club || !!clubMatch(c.s, S.wants.club))
      && (!S.wants.teiji || c.s.st === 'teiji' || c.s.tj === 1)) }));
  await pg.close();
  return { names, ...state };
}

// 部活: データにある部（軽音楽・剣道）で絞れ、全カードにその部があること
const keion = await ask(["町田", "45分以内", "20", "15", "350", "軽音楽をやりたい", "特にない"]);
check("部活名で絞れる（軽音楽）", keion.wants.club?.[0] === "軽音楽" && keion.names.length > 0,
  keion.names.join("・"));
check("出た学校すべてに希望の部がある", keion.ok === true);

// 定時制: 希望したら定時制のある学校（定時制のみ15校＋併設39校）に絞る（#20統一）
const teiji = await ask(["新宿", "30分以内", "15", "10", "250", "夜間の定時制も見たい", "特にない"]);
check("定時制の希望で定時制のある学校に絞る", teiji.names.length > 0 && teiji.ok !== false,
  teiji.names.join("・"));
check("定時制絞りで定時制のみの学校も出る", teiji.names.some((n) => ["新宿山吹","一橋","六本木","稔ヶ丘","浅草","大江戸"].includes(n)),
  teiji.names.join("・"));
const noTeiji = await ask(["新宿", "30分以内", "15", "10", "250", "特にありません", "特にない"]);
check("希望がなければ定時制は出ない",
  !noTeiji.names.some((n) => ["新宿山吹","一橋","六本木","稔ヶ丘","浅草","大江戸"].includes(n)),
  noTeiji.names.join("・"));

// 制服: 「制服がない学校」で制服なし校だけになる
const shifuku = await ask(["池袋", "30分以内", "22", "16", "400", "制服がない学校がいい", "特にない"]);
check("制服なしの希望で絞れる", shifuku.wants.uf === "no" && shifuku.names.length > 0,
  shifuku.names.join("・"));

// 満点近い子: 進学校が並び、エンカレッジ校が混ざらない
const high = await ask(["渋谷", "60分以内", "25", "20", "480", "大学進学に力を入れたい", "特にない"]);
check("満点近い子に進学校が複数出る", high.names.length >= 3, high.names.join("・"));
check("満点近い子にエンカレッジ校を混ぜない",
  !high.names.some((n) => ["蒲田","足立東","東村山","秋留台","中野工科"].includes(n)));

// 通学時間を「こだわらない」とテキストで打つ
const nolim = await ask(["八王子", "こだわらない", "22", "16", "400", "特にありません", "特にない"]);
check("「こだわらない」のテキスト入力が通る", nolim.limit === 999 && nolim.names.length > 0,
  `limit=${nolim.limit}`);

// 学科語と部活名の衝突: 「ものづくりがやりたい」を ものづくり部と誤解しない
const mono = await ask(["品川シーサイド", "40分以内", "18", "13", "300", "ものづくりがやりたい。定時制も見たい", "特にない"]);
check("「ものづくり」を学科として扱う（部活と誤解しない）", mono.wants.club == null && mono.wants.dept === "工",
  JSON.stringify({ club: mono.wants.club, dept: mono.wants.dept }));
// 定時制希望があるときは定時制に絞るので、高専・全日制のみは出ない（API #20と同じ）
check("複合希望（工業系＋定時制）は定時制のある工科に絞る",
  mono.names.length > 0 && !mono.names.some((n) => n.includes("高専")),
  mono.names.join("・"));
// 重視軸（#22のプロトタイプ版）
async function askPri(pri) {
  const pg = await browser.newPage({ viewport: { width: 1100, height: 900 }, reducedMotion: "reduce" });
  pg.on("pageerror", (e) => errors.push(String(e)));
  await pg.route("**://tile.openstreetmap.org/**", (r) => r.abort());
  await pg.goto(FILE);
  await pg.click("#startBtn");
  for (const t of ["新宿", "50分以内", "20", "16", "380", "特にありません", pri]) {
    await pg.fill("#input", t);
    await pg.press("#input", "Enter");
    await pg.waitForTimeout(350);
  }
  await pg.waitForTimeout(600);
  const rows = await pg.evaluate(() => S.shown.map((c) => ({ n: c.s.n, m: c.m, tier: c.tier, g: c.s.g || "" })));
  const pr = await pg.evaluate(() => S.wants.priority);
  await pg.close();
  return { rows, pr };
}
// チップと同じ文言をテキストで打つ人は多い（2026-08-22 実バグ: 「近さ」が
// 正規表現に無く、S4bで無限に聞き返されてマップが空のままだった）
const pcChip = await askPri("通学の近さ");
check("チップと同じ文言のテキスト入力が通る", pcChip.pr === "commute" && pcChip.rows.length > 0,
  `pr=${pcChip.pr} / ${pcChip.rows.length}校`);
const pc = await askPri("なるべく近いところがいいです");
check("「近いところがいい」で通学の近さ軸になる", pc.pr === "commute");
check("近さ最優先は近い順に並ぶ",
  pc.rows.every((r, i) => i === 0 || pc.rows[i - 1].m <= r.m),
  pc.rows.map((r) => `${r.n}${r.m}分`).join("→"));
const pa = await askPri("大学進学");
check("進学最優先で進学指導の指定校が先頭に来る", (pa.rows[0]?.g ?? "").includes("進学"),
  pa.rows.map((r) => `${r.n}(${r.g || "指定なし"})`).join("・"));
const pr2 = await askPri("いま届きそうなところ");
check("届きそう最優先は安全圏が先頭で挑戦圏を勧めない",
  pr2.rows.length > 0 && pr2.rows[0].tier === "s" && pr2.rows.every((r) => r.tier !== "c"),
  pr2.rows.map((r) => `${r.n}:${r.tier}`).join("・"));

/* モバイル幅でのチップのタップ（2026-08-23 実測バグ）。
   入力欄に打ったあとチップを押すと、blurでタブバーが戻ってレイアウトが
   56px跳ね、1回目のタップが外れて会話が止まっていた。 */
console.log("\n── モバイル幅のチップ操作 ──");
const mob = await browser.newPage({ viewport: { width: 430, height: 900 }, reducedMotion: "reduce" });
mob.on("pageerror", (e) => errors.push(String(e)));
await mob.route("**://tile.openstreetmap.org/**", (r) => r.abort());
await mob.goto(FILE);
await mob.click("#startBtn");
for (const t of ["練馬", "45分以内", "22", "16", "380", "吹奏楽をやりたい"]) {
  await mob.fill("#input", t);
  await mob.press("#input", "Enter");
  await mob.waitForTimeout(300);
}
await mob.waitForTimeout(500);
// 入力直後（キーボードが出ている状態）にチップを1回タップする
await mob.locator("#chips button", { hasText: "通学の近さ" }).click();
await mob.waitForTimeout(2500);
const mobState = await mob.evaluate(() => ({ state: S.state, cards: document.querySelectorAll(".card").length }));
await mob.close();
check("モバイル幅で入力直後のチップが1回で効く",
  mobState.state === "S6" && mobState.cards > 0,
  `state=${mobState.state} cards=${mobState.cards}`);

check("追加シナリオでJSの例外が出ていない", errors.length === 0, errors[0] ?? "");

/* ---- 2026-08-23 の画面の直し（西の指示5点）の再発防止 ---- */

/* 対話をひととおり済ませ、くらべるシートに3校入れた状態のページを作る */
async function seeded(viewport, answers = ["練馬", "40分以内", "22", "16", "380", "バスケがやりたい", "特にない"]) {
  const pg = await browser.newPage({ viewport, reducedMotion: "reduce" });
  pg.on("pageerror", (e) => errors.push(String(e)));
  await pg.route("**://tile.openstreetmap.org/**", (r) => r.abort());
  await pg.goto(FILE);
  await pg.click("#startBtn");
  for (const t of answers) {
    await pg.fill("#input", t);
    await pg.press("#input", "Enter");
    await pg.waitForTimeout(400);
  }
  await pg.waitForTimeout(700);
  const n = Math.min(3, await pg.locator(".card .cmp").count());
  for (let i = 0; i < n; i++) { await pg.locator(".card .cmp").nth(i).click(); await pg.waitForTimeout(120); }
  return pg;
}
const isOpen = (pg) => pg.locator("#sheet").evaluate((e) => e.classList.contains("open"));

console.log("\n── デスクトップ: くらべるシートは右のボードのタブ ──");
{
  // 全画面が覆いかぶさると、左の対話も候補カードも見えなくなる（#38後の指示）
  const pg = await seeded({ width: 1440, height: 900 });
  await pg.click("#tabCmp");
  await pg.waitForTimeout(600);
  check("ボードのタブにシートが出る", (await pg.locator("#bbody .cmpsheet").count()) === 1);
  check("全画面シートは開かない", !(await isOpen(pg)));
  check("ボードのシートに1枚地図が出る", (await pg.locator("#bbody .cmpsheet .ovmapwrap").count()) === 1);
  // 詳細表示もボードの中で切り替える
  await pg.locator("#bbody .sheet-detail[data-name]").first().click();
  await pg.waitForTimeout(500);
  check("詳細表示もボードの中", !(await isOpen(pg)) && (await pg.locator("#bbody .sheet-back").count()) === 1);
  await pg.locator("#bbody .sheet-back").click();
  await pg.waitForTimeout(500);
  const back = await pg.locator("#bbody .cmpsheet tbody tr:not(.cmphead)").count();
  check("詳細から一覧に戻れる", back === 3, `${back}校`);
  // 印刷はA4の1枚なので、そこだけ全画面シートを開く
  await pg.locator("#bbody .ovops .ghost").click();
  await pg.waitForTimeout(500);
  check("「印刷用に開く」で全画面シートが開く", await isOpen(pg));
  await pg.close();
}

console.log("\n── スマホ: シートは表のまま並べて比べる ──");
{
  /* 一度は1校ずつの縦カードに組み替えたが、8/23 に表へ戻した。
     縦に積むと1校ずつ読む画面になり、学校どうしを同じ行で見比べる
     という「くらべる」の目的そのものができなくなるため。 */
  const pg = await seeded({ width: 390, height: 844 });
  await pg.evaluate(() => window.openCompare());
  await pg.waitForTimeout(700);
  check("スマホは全画面シート", await isOpen(pg));
  const disp = await pg.locator("#sheetBody .cmpsheet table").evaluate((e) => getComputedStyle(e).display);
  check("表の形のまま出す", disp === "table", `display:${disp}`);
  const w = await pg.locator("#sheetBody .cmpwrap").evaluate((e) => [e.scrollWidth, e.clientWidth]);
  check("横スクロールが要らない", w[0] <= w[1] + 1, `${w[0]} <= ${w[1]}`);
  const labels = await pg.locator("#sheetBody .cmpsheet tr:not(.cmphead)").first()
    .evaluate((tr) => [...tr.querySelectorAll("td[data-l]")].map((td) => td.dataset.l));
  check("各項目に見出しが付く", labels.includes("合格の目安") && labels.includes("倍率5年推移"), labels.join("/"));
  /* ⚠️ td を grid にすると <br> で切れた文字列が**別のマス**に落ちる。
        中身は .v で包んで、必ず「見出し + 値」の2マスにする */
  const cells = await pg.locator("#sheetBody .cmpsheet tbody td[data-l]")
    .evaluateAll((tds) => tds.every((td) => td.children.length === 1 && td.firstElementChild.classList.contains("v")));
  check("値は1つの箱にまとまっている", cells);
  await pg.close();
}

console.log("\n── 特色の無い学校に肩書きを作らない ──");
{
  const pg = await seeded({ width: 1100, height: 900 });
  const tags = await pg.evaluate(() => D.schools.filter((s) => !s.x).map((s) => schoolTag(s)));
  // 部活は全校にあり、都大会の記録も広く出る。数や有無から作る肩書きは飾りにしかならない
  check("部活の数・有無から肩書きを作らない",
    !tags.some((t) => ["部活充実", "部活多数", "部活盛ん"].includes(t)));
  check("指定・実績のある学校には肩書きが残る", tags.filter(Boolean).length > 100,
    `${tags.filter(Boolean).length}校`);
  check("肩書きの無い学校は空欄にする", tags.filter((t) => !t).length > 0,
    `${tags.filter((t) => !t).length}校`);
  await pg.close();
}

console.log("\n── 全体から探す: 校名 → 通学時間 … 圏 → 区 ──");
{
  const pg = await seeded({ width: 1440, height: 900 });
  await pg.click("#tabAll");
  await pg.waitForTimeout(800);
  const order = await pg.evaluate(() => {
    const t = document.querySelector("#bbody .tier");
    if (!t) return null;
    const row = t.closest("div[style*='display:flex']");
    return [...row.children].map((k) => k.tagName + ":" + k.innerText.replace(/\s+/g, " ").trim());
  });
  check("並びは 校名 → 通学時間 →（圏 + 区）",
    order?.length === 3 && order[0].startsWith("B:")
    && /通学時間/.test(order[1]) && /圏/.test(order[2]) && /[区市町村]/.test(order[2]),
    JSON.stringify(order));
  await pg.close();
}

console.log("\n── 部活の男女 ──");
{
  const pg = await seeded({ width: 1100, height: 900 });
  const r = await pg.evaluate(() => {
    const s = D.schools.find((x) => x.n === "練馬");
    return {
      inWords: D.cw.filter((w) => /^(男子|女子|男女)/.test(w)).length,
      hit: clubMatch(s, findClubWords("バスケがやりたい")),
      bits: clubGender(s, "バスケットボール"),
      label: clubLabel("バスケットボール") + "あり" + genderNote(clubGender(s, "バスケットボール")),
      neutral: clubGender(s, "吹奏楽"),
    };
  });
  // 男女を種目名に混ぜると「バスケがしたい」に2語が当たり、同じ部が2件に見える
  check("種目名に男女を混ぜていない", r.inWords === 0, `${r.inWords}語`);
  check("「バスケがやりたい」が種目名1語に当たる", r.hit === "バスケットボール", String(r.hit));
  check("男女の別を持っている", r.bits === 3, String(r.bits));
  check("表示に男女が付く", r.label === "バスケットボール部あり（男子・女子）", r.label);
  check("男女で分けない部には付けない", r.neutral === 0);
  const badge = await pg.locator(".card .meta").first().innerText();
  check("カードのバッジにも出る", /部あり（(男子|女子|男子・女子)）/.test(badge), badge.slice(-30));
  await pg.close();
}

check("2026-08-23の画面でJSの例外が出ていない", errors.length === 0, errors[0] ?? "");

await browser.close();
const ng = results.filter((r) => !r.ok);
console.log(`\n${results.length - ng.length} / ${results.length} 件 通過`);
if (ng.length) { console.log("失敗:"); ng.forEach((r) => console.log(`  - ${r.name}`)); process.exit(1); }
console.log("すべて通過しました。");
