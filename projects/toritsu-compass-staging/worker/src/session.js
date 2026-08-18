/**
 * 対話セッションと、LLM呼び出し回数の上限（仕様書§3.6・実装必須）。
 *
 * 置き場所を2つに分けている。
 *
 *   KV  … 会話の中身（条件・聞いた項目・「わからない」と言われた項目）。TTL 24h
 *   D1  … LLM呼び出し回数だけ
 *
 * 回数をKVに置かないのは、KVが結果整合だから。書いた直後に読むと古い値が
 * 返ることがあり、上限の判定に使うと連打で簡単に突破される。クレジットは
 * チーム共通$100で、使い切ると誰も開発できなくなる。
 * D1 は読み書きが即時なので、数える役はこちらに任せる
 * （schema.sql の sessions テーブルにその旨のコメントがある）。
 */

const TTL_SEC = 60 * 60 * 24;          // 24時間（仕様書§6.4）

/** 1セッションで許すLLM呼び出しの回数。env.LLM_MAX_CALLS で上書きできる。 */
export const DEFAULT_MAX_LLM_CALLS = 30;

const kvKey = (id) => `session:${id}`;

export function maxLlmCalls(env) {
  const n = Number(env?.LLM_MAX_CALLS);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_MAX_LLM_CALLS;
}

/**
 * セッションを読む。無ければ作る。
 *
 * session_id は利用者から渡ってくるので、そのままKVの鍵にしない。
 * 形を検証して、通らなければ新しく採番する。
 */
export async function loadSession(env, rawId) {
  const id = typeof rawId === "string" && /^[0-9a-f-]{36}$/i.test(rawId)
    ? rawId
    : crypto.randomUUID();

  let state = null;
  try {
    state = await env.SESSIONS.get(kvKey(id), "json");
  } catch {
    state = null;                      // KVが読めなくても会話は続ける
  }

  const row = await env.DB.prepare(
    "SELECT llm_calls FROM sessions WHERE session_id = ?"
  ).bind(id).first().catch(() => null);

  return {
    id,
    created: !state,
    query: state?.query ?? null,
    asked: state?.asked ?? [],
    declined: state?.declined ?? [],
    llm_calls: row?.llm_calls ?? 0,
  };
}

/** 会話の中身をKVに書く。TTLを毎回付け直すので、使っている間は消えない。 */
export async function saveSession(env, session) {
  const body = JSON.stringify({
    query: session.query,
    asked: session.asked,
    declined: session.declined,
    updated_at: new Date().toISOString(),
  });
  try {
    await env.SESSIONS.put(kvKey(session.id), body, { expirationTtl: TTL_SEC });
  } catch {
    // KVが書けなくても会話は続ける。次のリクエストで条件を送り直せばよい
  }
}

/**
 * LLMを1回呼んでよいか。**呼ぶ前に必ず通す。**
 *
 * 上限を超えたら false を返す。会話は止めない。LLMを使わずに規則ベースだけで
 * 続ける（extract.js が二段構えになっているため、質は落ちるが動く）。
 * ここで会話ごと打ち切ると、上限に達した保護者が締め出される。
 */
export function canCallLLM(env, session) {
  return session.llm_calls < maxLlmCalls(env);
}

/**
 * 呼び出しを1回ぶん記録する。**実際に呼んだ後に呼ぶこと。**
 *
 * 行が無ければ作る。同じセッションに同時に複数のリクエストが来ても
 * 数え落とさないよう、SQL側で加算する（読んでから足して書く、をしない）。
 */
export async function recordLLMCall(env, session, count = 1) {
  const now = new Date().toISOString();
  try {
    await env.DB.prepare(
      `INSERT INTO sessions (session_id, created_at, updated_at, state, llm_calls)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(session_id) DO UPDATE SET
         llm_calls = llm_calls + excluded.llm_calls,
         updated_at = excluded.updated_at,
         state = excluded.state`
    ).bind(session.id, now, now, session.state ?? null, count).run();
    session.llm_calls += count;
  } catch {
    // 記録に失敗しても会話は続ける。ただし数えられていないので、
    // 安全側に倒して今回のぶんは使ったものとして扱う
    session.llm_calls += count;
  }
}

/** 画面やログに出すための残量。 */
export function budgetOf(env, session) {
  const max = maxLlmCalls(env);
  return {
    used: session.llm_calls,
    max,
    remaining: Math.max(0, max - session.llm_calls),
    exhausted: session.llm_calls >= max,
  };
}
