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
 */

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
  commute_times: 31703,
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    }

    try {
      if (path === "/health") return await handleHealth(env);
      if (path === "/health/ai") return await handleHealthAi(env);
      if (path === "/api/schools") return await handleSchoolList(env, url);

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
           FROM schools s JOIN commute_times c ON c.to_ward = s.ward
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
            level_band_draft
       FROM schools ${clause}
      ORDER BY school_number
      LIMIT ? OFFSET ?`
  )
    .bind(...binds, limit, offset)
    .all();

  return json({ total, limit, offset, count: results.length, schools: results });
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
