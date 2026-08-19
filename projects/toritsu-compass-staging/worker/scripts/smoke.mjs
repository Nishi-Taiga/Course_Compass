#!/usr/bin/env node
/* 本番（またはローカル）のAPIを実際に叩く通しテスト。
 *
 * 作った理由: Workers AI を有効化したとき、LLMの結果が毎回捨てられていたのに
 * 規則ベースが拾うため「正常に見えて」いた。返答の形が変わっても気づけないので、
 * 「LLMが実際に使われたか」まで確かめる。
 *
 * 使い方:
 *   node scripts/smoke.mjs                     # 本番
 *   node scripts/smoke.mjs http://localhost:8787
 */

const BASE = process.argv[2] || "https://toritsu-compass-staging.tokyo-odh-299.workers.dev";
const results = [];

function check(name, cond, detail = "") {
  results.push({ name, ok: !!cond, detail });
  console.log(`  ${cond ? "✅" : "❌"} ${name}${detail ? `  ${detail}` : ""}`);
}

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: r.status, json: await r.json().catch(() => null) };
}

console.log(`対象: ${BASE}\n`);

/* --- 1. 土台 ------------------------------------------------------- */
console.log("── 疎通 ──");
const health = await fetch(`${BASE}/health`).then((r) => r.json());
check("/health が ok", health.ok === true, health.ok ? "" : JSON.stringify(health.d1 ?? ""));
check("D1の件数が期待どおり", health.d1?.commute_times === health.expected?.commute_times,
  `${health.d1?.commute_times} / 期待 ${health.expected?.commute_times}`);
check("部活データが入っている", (health.d1?.school_clubs ?? 0) > 4000 || health.ok === true);

/* --- 2. 検索 ------------------------------------------------------- */
console.log("\n── 検索 ──");
const s1 = await post("/api/search", {
  station: "練馬", limit: 45, naishin5: 22, jitsugi: 10, exam_score: 390,
  wants: { clubs: ["吹奏楽"] },
});
check("部活で絞れる", s1.json?.count > 0, `${s1.json?.count}校`);
check("全件が通学時間の条件内",
  (s1.json?.schools ?? []).every((x) => x.commute_minutes <= 45),
  "※バインド順の不具合の回帰");
check("全件に希望の部活がある",
  (s1.json?.schools ?? []).every((x) => (x.matched_clubs ?? []).length > 0));

const s0 = await post("/api/search", {
  station: "練馬", limit: 45, naishin5: 22, jitsugi: 10, exam_score: 390,
  wants: { clubs: ["カーリング"] },
});
check("無い部活は0件になる", s0.json?.count === 0);
check("0件のとき緩和案を出す", (s0.json?.relaxation?.options ?? []).length > 0,
  `${(s0.json?.relaxation?.options ?? []).length}案`);

const sBad = await fetch(`${BASE}/api/search`, {
  method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ station: "存在しない駅", limit: 60 }),
});
check("駅名の打ち間違いは404", sBad.status === 404, `HTTP ${sBad.status}`);

/* --- 3. 抽出（LLMを含む） ------------------------------------------ */
console.log("\n── 抽出 ──");
const e1 = await post("/api/extract", {
  text: "石神井公園のあたりに住んでいて、子どもが吹奏楽をやりたいと言っています",
});
check("駅を抜ける", e1.json?.query?.station === "石神井公園", e1.json?.query?.station);
check("部活を抜ける", (e1.json?.query?.wants?.clubs ?? []).includes("吹奏楽"));
check("LLMが実際に使われた", e1.json?.source?.llm === "used",
  `llm=${e1.json?.source?.llm}`);

/* 言っていない項目を勝手に埋めないこと。
   当日点は下限が0なので、null が 0 として通った過去がある（実害あり）。 */
const e2 = await post("/api/extract", { text: "練馬に住んでいます" });
const q2 = e2.json?.query ?? {};
check("言っていない当日点を埋めない", q2.toujitsu == null, `toujitsu=${q2.toujitsu}`);
check("言っていない内申を埋めない", q2.naishin5 == null && q2.jitsugi == null);

const e3 = await post("/api/extract", {
  text: "内申は5教科が22、実技が10です。当日は390点くらいでした",
});
check("言った数値は正しく入る",
  e3.json?.query?.naishin5 === 22 && e3.json?.query?.jitsugi === 10 &&
  e3.json?.query?.toujitsu === 390,
  JSON.stringify({ n5: e3.json?.query?.naishin5, j: e3.json?.query?.jitsugi, t: e3.json?.query?.toujitsu }));

const e4 = await post("/api/extract", { text: "5教科は99です" });
check("範囲外は弾いて聞き直す", (e4.json?.invalid ?? []).includes("naishin5"),
  JSON.stringify(e4.json?.invalid));

/* --- 4. Workers AI ------------------------------------------------- */
console.log("\n── Workers AI ──");
const ai = await fetch(`${BASE}/health/ai`).then((r) => r.json()).catch(() => null);
check("/health/ai が応答する", ai?.ok === true, ai?.model ?? "");

/* --- まとめ -------------------------------------------------------- */
const ng = results.filter((r) => !r.ok);
console.log(`\n${results.length - ng.length} / ${results.length} 件 通過`);
if (ng.length) {
  console.log("失敗:");
  ng.forEach((r) => console.log(`  - ${r.name} ${r.detail}`));
  process.exit(1);
}
console.log("すべて通過しました。");
