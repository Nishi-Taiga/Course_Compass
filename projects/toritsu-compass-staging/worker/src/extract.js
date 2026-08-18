/**
 * 自由入力を「検索と判定が食べられる形」に変える翻訳層。
 *
 * 2026-08-13 MTGで決めたAIの役割は**翻訳係**であって、賢く高校を選ぶ係ではない。
 * ここがその実装。守っている決まりは3つ。
 *
 *   1. **AIの出力は候補文字列であって確定値ではない。**
 *      駅名も学科も、DBに実在するか照合して初めて確定する。
 *      これが「DBにある事実以外は出力させない」を入口側で担保する形。
 *   2. **数値の換算はコードがやる。** AIに「換算内申は41」と計算させない。
 *      AIは「5教科が25と言っている」までを渡すだけで、換算は scoring.js が持つ。
 *   3. **何が足りないかの判定はコード（query.js）。** AIには聞き返し文の
 *      言い回しだけを任せる。AIが落ちても聞き返しのループは壊れない。
 *
 * LLMが使えない状況（Workers AI の招待待ち）でも動くよう、規則ベースの抽出だけで
 * 完結する。env.AI があればそれを足して精度を上げる、という二段構えにしてある。
 */

import { CLUB_CATEGORIES } from "./search.js";

/* ------------------------------------------------------------------ */
/* 規則ベースの抽出（LLM無しで動く土台）                                */
/* ------------------------------------------------------------------ */

const toHalf = (s) =>
  s.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));

/**
 * 見出し語の近くにある数値を拾う。「5教科は25点」「実技が8」の両方に効く。
 *
 * ⚠️ ここでは範囲を見ない。「5教科は99」を黙って捨てると、利用者には
 *    無視された理由が分からない。値は拾って query.js に渡し、
 *    範囲外として聞き直させる。
 */
function numberNear(text, keyword, { max = 12 } = {}) {
  const m = text.match(new RegExp(`${keyword}[^0-9]{0,${max}}(\\d{1,3})`));
  return m ? Number(m[1]) : null;
}

const DEPT_WORDS = [
  [/工業|工科|ものづくり|機械|電気/, "工"],
  [/商業|ビジネス|簿記/, "商"],
  [/農業|農芸|園芸|畜産/, "農"],
  [/総合学科|総合高校|いろいろ学びたい/, "総"],
  [/家政|家庭|保育|調理|服飾/, "家"],
  [/福祉|介護/, "福"],
  [/水産|海洋/, "水"],
  [/普通科/, "普"],
];

const CLUB_WORDS = [...new Set(Object.values(CLUB_CATEGORIES).flat())];

// 「わかりません」「まだ受けてない」まで拾う。ここを取りこぼすと、
// 同じ質問を繰り返して保護者が離脱する。
const DECLINE_RE =
  /わか(?:ら|り)|分か(?:ら|り)|わかん|不明|決めてな|決まってな|まだ.{0,6}(?:受けて|出て|決めて)(?:い)?ない|持ってな/;

/**
 * 発話から条件の候補を拾う。**確定はしない。**
 * @returns {{cand:object, declined:string[], hits:string[]}}
 */
export function extractRules(raw) {
  const text = toHalf(String(raw ?? ""));
  const cand = {};
  const declined = [];
  const hits = [];

  // --- 駅。候補を出すだけで、実在確認は resolve 側 ---
  const st = text.match(/([一-龥ぁ-んァ-ヴー\w]{1,12}?)駅/)
    ?? text.match(/([一-龥ァ-ヴー]{2,12})(?:から|より)/)
    // 「高野台のあたり」のように駅と言わない人もいる。候補として拾うだけで、
    // 実在するかは resolveStation が決めるので、外しても害はない
    ?? text.match(/([一-龥ァ-ヴー]{2,12})(?:の?(?:あたり|付近|周辺|近く)|に住)/);
  if (st) { cand.station = st[1]; hits.push("station"); }

  // --- 通学時間。「30分かかる」ではなく上限を言っている場合だけ拾う ---
  const commute = text.match(/(\d{1,3})\s*分(?:以内|くらい|ぐらい|程度|まで)/)
    ?? (/通学|通え|かよ/.test(text) ? text.match(/(\d{1,3})\s*分/) : null);
  if (commute) {
    const v = Number(commute[1]);
    if (v > 0 && v <= 180) { cand.commute_limit = v; hits.push("commute_limit"); }
  }

  // --- 内申。5教科と実技を別々に。換算はここではやらない ---
  const n5 = numberNear(text, "(?:5|五)\s*教科");
  if (n5 != null) { cand.naishin5 = n5; hits.push("naishin5"); }

  const j4 = numberNear(text, "実技(?:\s*(?:4|四)\s*教科)?");
  if (j4 != null) { cand.jitsugi = j4; hits.push("jitsugi"); }

  const sonai = numberNear(text, "(?:9|九)\s*教科")
    ?? (n5 == null && j4 == null && !/換算/.test(text)
          ? numberNear(text, "(?:素)?内申") : null);
  if (sonai != null) { cand.sonai = sonai; hits.push("sonai"); }

  const kansan = numberNear(text, "換算内申");
  if (kansan != null) { cand.naishin = kansan; hits.push("naishin"); }

  const exam = numberNear(text, "(?:当日点|本番|模試|入試|得点)", { max: 14 });
  if (exam != null) { cand.toujitsu = exam; hits.push("toujitsu"); }

  // --- 重視すること ---
  const wants = {};
  if (/進学|大学|受験に強|学力|勉強/.test(text)) { wants.academic = true; hits.push("wants.academic"); }

  for (const [re, code] of DEPT_WORDS) {
    if (re.test(text)) { wants.dept = code; hits.push("wants.dept"); break; }
  }

  // 表記はページ・発話のまま残す（正規化は西が監修する後段の仕事）。
  // 「サッカー部」を「サッカー」に削ってしまうと元表記に戻せない。
  const clubs = [];
  for (const w of CLUB_WORDS) {
    const m = text.match(new RegExp(`${w}(?:部|同好会|クラブ)?`));
    if (m) clubs.push(m[0]);
  }
  if (clubs.length) { wants.clubs = clubs; hits.push("wants.clubs"); }
  if (Object.keys(wants).length) cand.wants = wants;

  // --- 「わからない」。どの項目についてかは呼び出し側が文脈で決める ---
  if (DECLINE_RE.test(text)) declined.push("__any__");

  return { cand, declined, hits };
}

/* ------------------------------------------------------------------ */
/* LLM（Workers AI）。使えないときは黙って規則ベースだけで進む          */
/* ------------------------------------------------------------------ */

const SYSTEM = `あなたは保護者の発話から、高校検索の条件を抜き出す変換器です。
次の規則を厳密に守ってください。

1. 発話に書かれていることだけを抜く。推測で補わない。
2. 計算しない。「5教科25、実技8」とあればそのまま2つの数として出す。
   換算内申や合計点は絶対に自分で計算しない。
3. 学校名・部活名・駅名は、発話に出てきた文字列のまま書く。正式名称に直さない。
4. 性別・家庭状況など、書かれていない属性を補わない。
5. 出力はJSONのみ。前置きも説明も付けない。分からない項目は null。

出力形式:
{"station":null,"commute_limit":null,"naishin5":null,"jitsugi":null,
 "sonai":null,"toujitsu":null,
 "wants":{"academic":false,"dept":null,"clubs":[]},
 "declined":[],"note":null}

declined には、本人が「分からない」「決めていない」と言った項目名を入れます
（station / commute_limit / naishin / toujitsu / wants のいずれか）。`;

/** LLMの返答からJSONを取り出す。前後に文が付いていても拾う。
 *
 * qwen3 は推論型なので <think>…</think> を前置きすることがある。
 * 中括弧がそこに含まれると壊れたJSONを掴むので、先に思考部分を落とす。
 * 見つからないときは、何が返ってきたのかを理由に含める（本番でしか
 * 再現しないため、応答を見ないと直しようがない）。 */
function parseJson(text) {
  let t = String(text ?? "")
    .replace(/<think>[\s\S]*?<\/think>/gi, "")   // 思考ブロック
    .replace(/<think>[\s\S]*$/i, "")             // 閉じtagが切れた場合
    .replace(/```(?:json)?/g, "")
    .trim();
  const start = t.indexOf("{");
  if (start < 0) {
    const head = t.slice(0, 120).replace(/\s+/g, " ");
    throw new Error(`JSONが見つかりません（応答の冒頭: ${head || "空"}）`);
  }
  return JSON.parse(t.slice(start, t.lastIndexOf("}") + 1));
}

/** LLMの出力を、こちらが認める形だけに削ぎ落とす。余計なキーは通さない。 */
function sanitize(obj) {
  const out = {};
  const n = (v, lo, hi) => {
    const x = Number(v);
    return Number.isFinite(x) && x >= lo && x <= hi ? x : null;
  };
  if (typeof obj.station === "string" && obj.station.trim()) out.station = obj.station.trim();
  const c = n(obj.commute_limit, 1, 180); if (c != null) out.commute_limit = c;
  const n5 = n(obj.naishin5, 5, 25); if (n5 != null) out.naishin5 = n5;
  const j4 = n(obj.jitsugi, 4, 20); if (j4 != null) out.jitsugi = j4;
  const so = n(obj.sonai, 9, 45); if (so != null) out.sonai = so;
  const tj = n(obj.toujitsu, 0, 500); if (tj != null) out.toujitsu = tj;

  const w = obj.wants ?? {};
  const wants = {};
  if (w.academic === true) wants.academic = true;
  if (typeof w.dept === "string" && w.dept.trim()) wants.dept = w.dept.trim();
  if (Array.isArray(w.clubs)) {
    const clubs = w.clubs.filter((x) => typeof x === "string" && x.trim()).map((x) => x.trim());
    if (clubs.length) wants.clubs = clubs;
  }
  if (Object.keys(wants).length) out.wants = wants;

  const declined = Array.isArray(obj.declined)
    ? obj.declined.filter((x) => typeof x === "string")
    : [];
  return { cand: out, declined };
}

/**
 * LLMに条件抽出をさせる。**失敗しても例外を投げない。**
 *
 * JSONが壊れるのは前提。1回だけ言い直させ、それでも駄目なら null を返して
 * 規則ベースの結果だけで進む。ここで throw すると画面が落ちる（仕様書§3.6）。
 */
export async function extractLLM(env, text) {
  if (!env?.AI) return { ok: false, reason: "ai_unavailable" };
  const model = env.AI_MODEL || "@cf/qwen/qwen3-30b-a3b-fp8";

  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await env.AI.run(model, {
        messages: [
          { role: "system", content: SYSTEM },
          {
            role: "user",
            content: attempt === 1
              ? text
              : `${text}\n\n（前回の返答はJSONとして読めませんでした。JSONだけを返してください）`,
          },
        ],
        // 推論型モデルは思考に枠を使う。512だとJSONに届かないことがある
        max_tokens: 1024,
      });
      const raw = typeof res === "string" ? res : (res?.response ?? "");
      return { ok: true, ...sanitize(parseJson(raw)), attempts: attempt };
    } catch (e) {
      if (attempt === 2) return { ok: false, reason: String(e?.message ?? e) };
    }
  }
  return { ok: false, reason: "unknown" };
}

/* ------------------------------------------------------------------ */
/* 実在照合。ここを通って初めて「確定値」になる                         */
/* ------------------------------------------------------------------ */

/** 駅名をDBに突き合わせる。候補が出せるときは候補も返す。 */
export async function resolveStation(db, name) {
  if (!name) return { station: null, candidates: [] };
  const clean = String(name).replace(/駅$/, "").trim();

  const exact = await db.prepare("SELECT station_name FROM stations WHERE station_name = ?")
    .bind(clean).first();
  if (exact) return { station: exact.station_name, candidates: [] };

  const { results } = await db
    .prepare("SELECT station_name FROM stations WHERE station_name LIKE ? LIMIT 5")
    .bind(`%${clean}%`).all();
  const candidates = results.map((r) => r.station_name);
  // 1件だけなら言い換えとみなして採用する（「練馬高野台」等の言い落とし対策）
  return { station: candidates.length === 1 ? candidates[0] : null, candidates };
}

/** 学科コードを実在値に突き合わせる。LLMが「工業」と書いても「工」に直す。 */
export function resolveDept(value) {
  if (!value) return null;
  const s = String(value).trim();
  const known = ["普", "工", "商", "農", "総", "家", "福", "水", "他"];
  if (known.includes(s)) return s;
  for (const [re, code] of DEPT_WORDS) if (re.test(s)) return code;
  return null;
}

/* ------------------------------------------------------------------ */
/* まとめ役                                                            */
/* ------------------------------------------------------------------ */

/**
 * 直前に何を尋ねたかを踏まえて、短い返事を読む。
 *
 * 「石神井公園です」「22」のような直答は、文だけ見ても何の値か分からない。
 * 質問した項目が分かっていれば読めるので、規則ベースで拾えなかったときの
 * 最後の受け皿にする。**尋ねた項目にしか当てはめない**（尋ねていない項目に
 * 数字を入れると、まったく違う条件で検索することになる）。
 */
function applyContext(cand, raw, askedSlot, prev) {
  if (!askedSlot) return;
  const text = toHalf(String(raw ?? "")).trim();
  const bare = text.match(/^(\d{1,3})\s*(?:点|分)?[。.\s]*$/);

  if (askedSlot === "station" && !cand.station) {
    // ⚠️ 発話から他の条件が取れているなら、駅の答えではない。
    //    「45分以内で」を駅名として扱うと、以降の回答も全部駅と誤読して
    //    会話が抜けられなくなる（駅が埋まらない限り asked_slot が station のままのため）
    if (Object.keys(cand).length) return;
    const name = text
      .replace(/[。.\s]+$/, "")
      .replace(/(?:駅)?(?:です|でお願いします|になります|かな|だと思います)$/, "")
      .replace(/駅$/, "");
    if (name && name.length <= 12) cand.station = name;
    return;
  }
  if (askedSlot === "commute_limit" && cand.commute_limit == null && bare) {
    cand.commute_limit = Number(bare[1]);
    return;
  }
  if (askedSlot === "naishin" && bare
      && cand.naishin5 == null && cand.jitsugi == null
      && cand.sonai == null && cand.naishin == null) {
    // 先に5教科を聞いているので、5教科が埋まっていれば次の数字は実技
    if (prev.naishin5 == null) cand.naishin5 = Number(bare[1]);
    else cand.jitsugi = Number(bare[1]);
  }
}

/**
 * 発話 → 条件の候補。規則ベースとLLMを重ねる。
 *
 * 数値と駅は規則ベースを優先する（正規表現のほうが確実で、LLMは桁を写し間違える）。
 * LLMには、規則ベースが取れなかった項目と、言い回しの揺れた意図を任せる。
 */
export async function extractQuery(env, db, text, { askedSlot = null, prev = {}, allowLLM = true } = {}) {
  const rules = extractRules(text);
  // allowLLM=false は、そのセッションが呼び出し上限に達しているとき（仕様書§3.6）。
  // 会話は止めず、規則ベースだけで続ける
  const llm = allowLLM ? await extractLLM(env, text) : { ok: false, reason: "budget_exhausted" };

  const cand = { ...(llm.ok ? llm.cand : {}), ...rules.cand };
  if (llm.ok && llm.cand.wants) {
    cand.wants = { ...llm.cand.wants, ...(rules.cand.wants ?? {}) };
  }

  applyContext(cand, text, askedSlot, prev);

  // 「わからない」は、いま尋ねている項目に対する返事として扱う。
  // どの項目か分からないまま declined に積むと、聞いていない項目まで
  // 飛ばしてしまうため。
  const declined = new Set(llm.ok ? llm.declined : []);
  if (rules.declined.includes("__any__") && askedSlot) declined.add(askedSlot);
  declined.delete("__any__");

  // --- 実在照合 ---
  const notes = [];
  let stationCandidates = [];

  // 何も見当が付かないときだけ、発話まるごとを駅名として**完全一致**で当てる。
  // 「石神井公園です」のように、駅とも言わず「〜のあたり」とも言わない人がいる。
  // 部分一致は使わない（関係ない語がたまたま当たると、勝手に駅が決まってしまう）
  if (!cand.station && Object.keys(cand).length === 0) {
    const bare = String(text).trim()
      .replace(/[。.\s]+$/, "")
      .replace(/(?:駅)?(?:です|でお願いします|になります|かな|だと思います)$/, "")
      .replace(/駅$/, "");
    if (bare && bare.length <= 12) {
      const hit = await db.prepare("SELECT station_name FROM stations WHERE station_name = ?")
        .bind(bare).first().catch(() => null);
      if (hit) cand.station = hit.station_name;
    }
  }
  if (cand.station) {
    const r = await resolveStation(db, cand.station);
    if (r.station) {
      cand.station = r.station;
    } else {
      stationCandidates = r.candidates;
      notes.push(
        r.candidates.length
          ? `「${cand.station}」に近い駅が複数あります: ${r.candidates.join("・")}`
          : `「${cand.station}」という駅が通学時間データに見つかりませんでした`
      );
      delete cand.station;
    }
  }
  if (cand.wants?.dept) {
    const dept = resolveDept(cand.wants.dept);
    if (dept) cand.wants.dept = dept;
    else { notes.push(`学科「${cand.wants.dept}」は特定できませんでした`); delete cand.wants.dept; }
  }

  return {
    cand,
    declined: [...declined],
    notes,
    station_candidates: stationCandidates,
    source: {
      rules: rules.hits,
      llm: llm.ok ? "used" : `skipped(${llm.reason})`,
      llm_attempts: llm.attempts ?? 0,
    },
  };
}

/** 既存の条件に、抽出した候補を重ねる。空の値で既存を潰さない。 */
export function mergeQuery(prev, cand) {
  const next = { ...prev, wants: { ...prev.wants } };
  for (const [k, v] of Object.entries(cand)) {
    if (k === "wants") continue;
    if (v != null && v !== "") next[k] = v;
  }
  const w = cand.wants ?? {};
  if (w.academic) next.wants.academic = true;
  if (w.dept) next.wants.dept = w.dept;
  if (w.clubs?.length) next.wants.clubs = [...new Set([...next.wants.clubs, ...w.clubs])];
  return next;
}
