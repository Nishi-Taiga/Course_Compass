/**
 * 都立進路コンパス — 疎通確認用 Worker
 *
 * アプリ本体ではない。D1 / KV / Workers AI が「提供された本番アカウントで実際に動く」
 * ことを1回で証明するためだけのもの。
 *
 *   GET /health      … D1 の実クエリ + KV の書き→読み→消し 往復
 *   GET /health/ai   … Workers AI を1回だけ呼ぶ（クレジット消費のため /health と分離）
 *   GET /api/schools … 学校一覧（ward / designation / q で絞り込み）
 *   GET /api/schools/:school_number … 学校詳細 + 応募倍率
 *   POST /api/search … 対話から組み立てた条件で候補校を返す（LLMは使わない）
 *   POST /api/extract … 自由入力を検索条件に翻訳し、足りない項目を聞き返す
 */

import { searchSchools, buildRelaxation } from "./search.js";
import { SCALE, GAP, GAP_ROUGH } from "./scoring.js";
import { parseQuery, inspect, invalidMessages } from "./query.js";
import { extractQuery, mergeQuery } from "./extract.js";
import { loadSession, saveSession, canCallLLM, recordLLMCall, budgetOf } from "./session.js";
import {
  interpretRelaxation, acceptedMessage, chooseMessage, DECLINED_MESSAGE, RELAX_LABELS,
} from "./relax.js";
import { explainResults } from "./explain.js";

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "cache-control": "no-store",
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body, null, 2), { status, headers: JSON_HEADERS });

/** 期待値。ここと実測が一致して初めて「通った」と言える。 */
const EXPECTED = {
  schools: 187,
  school_stats: 1314,
  designations: 29,
  stations: 647,
  // 通学時間を「駅→区」から「駅→学校」に変えた時点で 31,703 → 103,958 に増えた。
  // 期待値が古いままだと /health が恒久的に ok:false になり、
  // 本当に投入漏れが起きたときに気づけない。
  commute_times: 103958,
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    }

    try {
      if (path === "/health") return await handleHealth(env);
      if (path === "/health/ai") {
        // Workers AI のクレジットを消費するため乱打を止める。
        // URLが審査資料に載った瞬間から誰でも叩ける前提で、1時間6回まで。
        const hourKey = `health_ai_calls:${new Date().toISOString().slice(0, 13)}`;
        const calls = parseInt((await env.SESSIONS.get(hourKey)) ?? "0", 10);
        if (calls >= 6) {
          return json({ ok: false, error: "rate_limited",
                        hint: "AIクレジット保護のため1時間に6回まで" }, 429);
        }
        await env.SESSIONS.put(hourKey, String(calls + 1), { expirationTtl: 3600 });
        return await handleHealthAi(env);
      }
      if (path === "/api/schools") return await handleSchoolList(env, url);
      if (path === "/api/extract") {
        if (request.method !== "POST") {
          return json({ error: "method_not_allowed", expected: "POST" }, 405);
        }
        return await handleExtract(env, request);
      }
      if (path === "/api/search") {
        if (request.method !== "POST") {
          return json({ error: "method_not_allowed", expected: "POST" }, 405);
        }
        return await handleSearch(env, request);
      }

      const detail = path.match(/^\/api\/schools\/([^/]+)$/);
      if (detail) return await handleSchoolDetail(env, decodeURIComponent(detail[1]));

      return json({ error: "not_found", path }, 404);
    } catch (err) {
      // 想定外の例外も JSON で返す（ダッシュボードのログを見に行かなくて済むように）
      return json({ error: "unhandled", message: String(err?.message ?? err) }, 500);
    }
  },
};

/* ------------------------------------------------------------------ */
/* /health : D1 + KV                                                   */
/* ------------------------------------------------------------------ */

async function handleHealth(env) {
  const result = {
    ok: false,
    checked_at: new Date().toISOString(),
    d1: { ok: false },
    kv: { ok: false },
  };

  // --- D1: 実際にテーブルを数える（接続だけでなく投入済みかも見る） ---
  const d1Start = Date.now();
  try {
    const [schools, stats, designations, stations, commute, nerima] = await env.DB.batch([
      env.DB.prepare("SELECT COUNT(*) AS n FROM schools"),
      env.DB.prepare("SELECT COUNT(*) AS n FROM school_stats"),
      env.DB.prepare("SELECT COUNT(*) AS n FROM schools WHERE designation IS NOT NULL"),
      env.DB.prepare("SELECT COUNT(*) AS n FROM stations"),
      env.DB.prepare("SELECT COUNT(*) AS n FROM commute_times"),
      // Step3 の受け入れ条件そのもの。結合が実際に効くところまで見る。
      env.DB.prepare(
        `SELECT COUNT(*) AS n
           FROM schools s JOIN commute_times c ON c.school_number = s.school_number
          WHERE c.from_station = '練馬' AND c.minutes <= 60
            AND s.course_types LIKE '%全日制%'`
      ),
    ]);

    result.d1 = {
      ok: true,
      ms: Date.now() - d1Start,
      schools: schools.results[0].n,
      school_stats: stats.results[0].n,
      designations: designations.results[0].n,
      stations: stations.results[0].n,
      commute_times: commute.results[0].n,
      sample_query: {
        q: "練馬駅から60分以内・全日制",
        schools: nerima.results[0].n,
      },
    };
  } catch (err) {
    result.d1 = {
      ok: false,
      ms: Date.now() - d1Start,
      error: String(err?.message ?? err),
      hint: "テーブルが無い場合は npm run db:local / npm run db:remote を実行",
    };
  }

  // --- KV: 書いて読んで消す往復 ---
  const kvStart = Date.now();
  const key = `health:${crypto.randomUUID()}`;
  const expected = `ok-${Date.now()}`;
  try {
    await env.SESSIONS.put(key, expected, { expirationTtl: 60 });
    const actual = await env.SESSIONS.get(key);
    await env.SESSIONS.delete(key);
    result.kv = {
      ok: actual === expected,
      ms: Date.now() - kvStart,
      roundtrip: actual === expected ? "write→read→delete 成功" : `不一致: ${actual}`,
    };
  } catch (err) {
    result.kv = { ok: false, ms: Date.now() - kvStart, error: String(err?.message ?? err) };
  }

  // 件数が期待値どおりでなければ ok にしない（--local と --remote の取り違え検出）
  const counts_match = Object.keys(EXPECTED).every(
    (k) => result.d1[k] === EXPECTED[k]
  );

  result.ok = result.d1.ok && result.kv.ok && counts_match;
  result.schools = result.d1.schools ?? 0;
  result.expected = EXPECTED;

  if (result.d1.ok && !counts_match) {
    result.hint =
      "D1 には繋がっているが件数が想定と違う。--local と --remote は別のDBなので、" +
      "本番なら npm run db:remote を実行したか確認すること。";
  }

  return json(result, result.ok ? 200 : 503);
}

/* ------------------------------------------------------------------ */
/* /health/ai : Workers AI を1回だけ                                    */
/* ------------------------------------------------------------------ */

async function handleHealthAi(env) {
  const model = env.AI_MODEL ?? "@cf/qwen/qwen3-30b-a3b-fp8";

  // 招待待ちの間は wrangler.jsonc の ai をコメントアウトしてあるため未定義になる。
  if (!env.AI) {
    return json(
      {
        ok: false,
        error: "ai_binding_disabled",
        hint:
          "wrangler.jsonc の \"ai\" がコメントアウトされている。" +
          "ハッカソン用チームの招待を承認したら戻すこと。",
      },
      503
    );
  }

  // 日本語の対話品質も同時に見る（LLM選定ゲートの入力になるため、出力はそのまま残す）
  const messages = [
    {
      role: "system",
      content:
        "あなたは東京都立高校の進路相談にのるアシスタントです。保護者にわかる言葉で、簡潔に答えてください。",
    },
    {
      role: "user",
      content:
        "中学3年の子どもの志望校を考えています。都立高校の「進学指導重点校」とは何か、2〜3文で説明してください。",
    },
  ];

  const started = Date.now();
  try {
    const res = await env.AI.run(model, { messages, max_tokens: 512 });
    const text =
      typeof res === "string" ? res : res?.response ?? JSON.stringify(res);

    return json({
      ok: true,
      model,
      ms: Date.now() - started,
      prompt: messages[1].content,
      response: text,
      note: "クレジットを消費するため、繰り返し叩かないこと",
    });
  } catch (err) {
    return json(
      {
        ok: false,
        model,
        ms: Date.now() - started,
        error: String(err?.message ?? err),
        hint:
          "モデルIDが違う可能性がある。ダッシュボードの Workers AI → Model Catalog で " +
          "実際のIDを確認し、wrangler.jsonc の vars.AI_MODEL を直すこと。",
      },
      502
    );
  }
}

/* ------------------------------------------------------------------ */
/* /api/schools                                                        */
/* ------------------------------------------------------------------ */

async function handleSchoolList(env, url) {
  const ward = url.searchParams.get("ward");
  const designation = url.searchParams.get("designation");
  const q = url.searchParams.get("q");
  const limit = Math.min(Number(url.searchParams.get("limit")) || 50, 200);
  const offset = Math.max(Number(url.searchParams.get("offset")) || 0, 0);

  const where = [];
  const binds = [];

  if (ward) {
    where.push("ward = ?");
    binds.push(ward);
  }
  if (designation) {
    where.push("designation = ?");
    binds.push(designation);
  }
  if (q) {
    where.push("(name LIKE ? OR name_kana LIKE ?)");
    binds.push(`%${q}%`, `%${q}%`);
  }

  const clause = where.length ? `WHERE ${where.join(" AND ")}` : "";

  const total = await env.DB.prepare(`SELECT COUNT(*) AS n FROM schools ${clause}`)
    .bind(...binds)
    .first("n");

  const { results } = await env.DB.prepare(
    `SELECT school_number, name, name_kana, ward, address, course_types,
            departments, students_fulltime, designation, designation_rank,
            target_score, selection_type, score_layer
       FROM schools ${clause}
      ORDER BY school_number
      LIMIT ? OFFSET ?`
  )
    .bind(...binds, limit, offset)
    .all();

  return json({ total, limit, offset, count: results.length, schools: results });
}

/* ------------------------------------------------------------------ */
/* POST /api/search                                                    */
/* ------------------------------------------------------------------ */

async function handleSearch(env, request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  // 入力の検証は query.js に寄せてある。人が入力した条件も、AIが抽出した条件も
  // 同じ門を通す（2026-08-13 MTG決定の受け入れ基準）。
  const { q, invalid } = parseQuery(body);

  if (!q.station) {
    return json({ error: "station_required", hint: "出発駅を指定してください" }, 400);
  }

  // 駅名の打ち間違いを「0件」として返すと、緩和しても永遠に見つからない。
  // 見つからないのが条件のせいなのか駅名のせいなのかを、ここで切り分ける。
  const known = await env.DB.prepare(
    "SELECT 1 FROM commute_times WHERE from_station = ? LIMIT 1"
  ).bind(q.station).first();
  if (!known) {
    return json({
      error: "unknown_station",
      station: q.station,
      hint: "その駅は通学時間データにありません。駅名をご確認ください（例: 練馬）",
    }, 404);
  }
  if (!Number.isFinite(q.commute_limit) || q.commute_limit <= 0) q.commute_limit = 60;

  const started = Date.now();
  const { student, rows, all, mode } = await searchSchools(env.DB, q);

  // session_id が来ていれば、提案した緩和を覚えておく。
  // 次の発話「通学を広げて」が何に対する返事なのかを、会話側が知るため。
  const session = body.session_id ? await loadSession(env, body.session_id) : null;

  // 0件なら、何を緩めるかを明示して返す。黙って条件を外さない。
  if (!rows.length) {
    const relaxation = buildRelaxation(q);
    if (session) {
      session.query = q;
      session.relaxation_offered = (relaxation.options ?? []).map((o) => o.key);
      await saveSession(env, session);
    }
    const emptyPayload = {
      student, mode: student.score == null ? "commute_only" : "scored", count: 0, schools: [],
    };
    const emptyExplain = await explainResults(env, q, emptyPayload, { allowLLM: false });
    return json({
      query: q,
      student: {
        ...student,
        scale: SCALE.max,
        thresholds: student.rough ? GAP_ROUGH : GAP,
      },
      mode: emptyPayload.mode,
      count: 0,
      schools: [],
      summary: emptyExplain.text,
      relaxation,
      session_id: session?.id,
      // 範囲外の値は使わずに検索している。何を無視したかを黙っておかない
      invalid,
      invalid_messages: invalidMessages(invalid),
      ms: Date.now() - started,
    });
  }

  if (session) {
    session.query = q;
    session.relaxation_offered = [];     // 見つかったので、前の提案は無効
    await saveSession(env, session);
  }

  // 出口（S6）。レコードにある値だけで説明文を作る。LLMがあれば言い回しを
  // 自然にし、無ければ・壊れたら定型文に落ちる（入口と同じ二段構え）。
  const payload = { student, mode, count: rows.length, schools: rows };
  const explained = await explainResults(env, q, payload, {
    allowLLM: session ? canCallLLM(env, session) : true,
  });
  if (session && explained.llm_attempts) {
    await recordLLMCall(env, session, explained.llm_attempts);
  }

  return json({
    query: q,
    session_id: session?.id,
    student: {
      ...student,
      scale: SCALE.max,
      thresholds: student.rough ? GAP_ROUGH : GAP,
    },
    mode,             // scored = 点数判定あり / commute_only = 成績なし経路
    count: rows.length,
    candidates_before_pick: all.length,
    summary: explained.text,              // 全体の説明（S6）
    summary_source: explained.source,     // llm / template のどちらで作ったか
    schools: rows.map((s) => {
      const one = explained.per_school.find((p) => p.school_number === s.school_number);
      return one ? { ...s, explanation: one.text } : s;
    }),
    relaxation: null,
    invalid,
    invalid_messages: invalidMessages(invalid),
    disclaimer:
      "目安点は公開データをもとにした暫定値です。合否を保証するものではありません。"
      + "最終的な判断は学校の募集要項と、塾・学校の先生にご相談ください。",
    ms: Date.now() - started,
  });
}

/* ------------------------------------------------------------------ */
/* POST /api/extract                                                   */
/*                                                                     */
/* 自由入力を検索条件に翻訳する。AIの役割はここだけ（2026-08-13 MTG決定）。 */
/* 進行・検索・判定はコードが握る。                                      */
/* ------------------------------------------------------------------ */

async function handleExtract(env, request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const text = String(body.text ?? "").trim().slice(0, 1000);
  if (!text) {
    return json({ error: "text_required", hint: "発話を text に入れてください" }, 400);
  }

  // セッション。会話の中身はKV（TTL 24h）、LLMの呼び出し回数はD1で数える。
  // session_id を渡してもらえば、条件を毎回送り直さなくてよい。
  const session = await loadSession(env, body.session_id);

  // 明示的に query が来ていればそれを優先し、無ければセッションの続きから
  const { q: prev, invalid: prevInvalid } = parseQuery(body.query ?? session.query ?? {});
  const asked = Array.isArray(body.asked) ? body.asked.map(String) : session.asked;
  const declinedIn = Array.isArray(body.declined) ? body.declined.map(String) : session.declined;

  // 直前に緩和を提案していたら、まずその返事として読む。
  // 「通学を広げて」を条件の抽出に回すと何も取れず、承諾が成立しない（仕様書§5.3）。
  const offered = Array.isArray(body.relaxation_offered) && body.relaxation_offered.length
    ? body.relaxation_offered.map(String)
    : session.relaxation_offered;
  if (offered.length) {
    const reply = interpretRelaxation(text, offered);
    if (reply.key || reply.declined || reply.ambiguous) {
      const answered = await handleRelaxationReply(env, session, prev, text, offered, reply, asked, declinedIn);
      if (answered) return answered;
    }
  }

  // 上限に達していたらLLMを呼ばない。会話は規則ベースで続ける（仕様書§3.6）
  const allowLLM = canCallLLM(env, session);

  let extracted;
  try {
    extracted = await extractQuery(env, env.DB, text, {
      askedSlot: body.asked_slot ?? null,
      prev,
      allowLLM,
    });
    if (extracted.source.llm_attempts) {
      await recordLLMCall(env, session, extracted.source.llm_attempts);
    }
  } catch (e) {
    // 抽出が丸ごと失敗しても、会話は止めない。聞き直しに落とす（仕様書§3.6）
    return json({
      session_id: session.id,
      query: prev,
      filled: [],
      question: "うまく読み取れませんでした。もう一度、別の言い方で教えていただけますか？",
      next: null,
      llm_budget: budgetOf(env, session),
      error_handled: String(e?.message ?? e),
    });
  }

  const merged = mergeQuery(prev, extracted.cand);
  // 抽出結果もparseQueryを通す。LLM由来でも人由来でも同じ門を通す
  const { q, invalid: nowInvalid } = parseQuery({ ...merged, free_text: [...prev.free_text, text] });
  const invalid = [...new Set([...prevInvalid, ...nowInvalid])];

  const declined = [...new Set([...declinedIn, ...extracted.declined])];
  const state = inspect(q, asked, declined);

  // 聞き返しの優先順。困っていることから先に片付ける。
  //   ① 範囲外の値がある → まずそれを直してもらう
  //   ② 駅の候補が絞れない → 候補を並べて選んでもらう。ここで
  //      ただ「駅を教えてください」と返すと、同じ答えが返ってきて堂々巡りになる
  //   ③ それ以外 → 次に足りない項目を聞く
  const messages = invalidMessages(invalid);
  let question = state.question;
  if (messages.length) {
    question = messages.join("。");
  } else if (!q.station && extracted.station_candidates.length) {
    question = `${extracted.station_candidates.join("・")} のどれでしょうか。`;
  }

  // 次の発話でそのまま続けられるよう、会話の中身を保存する
  const nextAsked = state.next && !asked.includes(state.next) ? [...asked, state.next] : asked;
  session.query = q;
  session.asked = nextAsked;
  session.declined = declined;
  session.state = state.next;
  // 別の話を始めたら、前の緩和提案は無効にする
  session.relaxation_offered = [];
  await saveSession(env, session);

  return json({
    session_id: session.id,               // 次のリクエストでこれを渡せば条件を送り直さなくてよい
    query: q,
    filled: Object.keys(extracted.cand),
    declined,
    asked: nextAsked,
    invalid,
    notes: extracted.notes,               // 駅が特定できなかった等
    station_candidates: extracted.station_candidates,
    searchable: state.searchable,
    missing_required: state.missing_required,
    pending: state.pending,
    next: state.next,
    question,
    source: extracted.source,             // 規則ベース/LLMのどちらが効いたか
    llm_budget: budgetOf(env, session),   // 仕様書§3.6の呼び出し上限
  });
}

/**
 * 緩和の提案への返事を処理する。
 *
 * ⚠️ 一度に1つだけ適用する（仕様書§5.3の「段階を踏む」）。まとめて広げると、
 *    何が効いて見つかったのかが利用者にも我々にも分からなくなる。
 * ⚠️ 何を広げたかを必ず言葉で返す。黙って条件を外さない。
 */
async function handleRelaxationReply(env, session, prev, text, offered, reply, asked, declinedIn) {
  const base = {
    session_id: session.id,
    filled: [],
    declined: declinedIn,
    asked,
    invalid: [],
    notes: [],
    station_candidates: [],
    llm_budget: budgetOf(env, session),
  };

  if (reply.ambiguous) {
    // 決め打ちしない。どれを広げるか選び直してもらう
    return json({
      ...base,
      query: prev,
      relaxation_offered: offered,
      searchable: Boolean(prev.station),
      next: "relaxation",
      question: chooseMessage(offered, RELAX_LABELS),
      source: { rules: ["relaxation_ambiguous"], llm: "not_used", llm_attempts: 0 },
    });
  }

  if (reply.declined) {
    session.relaxation_offered = [];
    session.query = prev;
    await saveSession(env, session);
    return json({
      ...base,
      query: prev,
      relaxation_offered: [],
      searchable: Boolean(prev.station),
      next: null,
      question: DECLINED_MESSAGE,
      source: { rules: ["relaxation_declined"], llm: "not_used", llm_attempts: 0 },
    });
  }

  const q = {
    ...prev,
    relaxations: [...new Set([...(prev.relaxations ?? []), reply.key])],
    free_text: [...prev.free_text, text],
  };
  session.query = q;
  session.relaxation_offered = [];       // 承諾は1回で使い切る
  await saveSession(env, session);

  return json({
    ...base,
    query: q,
    filled: ["relaxations"],
    relaxation_applied: reply.key,
    relaxation_offered: [],
    searchable: Boolean(q.station),
    next: null,
    // 何を広げたかを明示してから検索し直す
    question: acceptedMessage(reply.key, q),
    source: { rules: ["relaxation_accepted"], llm: "not_used", llm_attempts: 0 },
  });
}

async function handleSchoolDetail(env, schoolNumber) {
  const school = await env.DB.prepare("SELECT * FROM schools WHERE school_number = ?")
    .bind(schoolNumber)
    .first();

  if (!school) return json({ error: "school_not_found", school_number: schoolNumber }, 404);

  const { results: stats } = await env.DB.prepare(
    `SELECT year, department, sub_department, capacity, applicants, ratio
       FROM school_stats
      WHERE school_number = ?
      ORDER BY year DESC, department`
  )
    .bind(schoolNumber)
    .all();

  return json({ school, stats });
}
