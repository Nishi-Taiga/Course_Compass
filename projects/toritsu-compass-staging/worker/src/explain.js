/**
 * 出口（S6）。検索結果を保護者に伝わる日本語にする。
 *
 * 作業ガイド Step5 の「出口（S6）: 検索結果のレコードを渡して自然語で説明。
 * **渡した値以外は書かせない**」がここ。
 *
 * ⚠️ この層は**事実を作らない**。文章に出てよいのは、検索結果のレコードに
 *    入っている値だけ。学校の評判・雰囲気・進学実績のような、DBに無いことは
 *    一切書かない。LLMを使う場合も、渡したJSONの値だけを使うよう指示し、
 *    壊れたら定型文に落とす。
 *
 * 入口（extract.js）と同じ二段構えにしてある。
 *   規則ベース（定型文）… Cloudflareが無くても動く。これが土台
 *   LLM              … env.AI があれば言い回しを自然にする。失敗したら土台に戻る
 */

/* ------------------------------------------------------------------ */
/* 定型文。LLMが無くても、これだけで意味の通る説明になる                 */
/* ------------------------------------------------------------------ */

/** 検索条件を1文にする。何で絞ったのかを最初に確認できるように。 */
function conditionText(q, student) {
  const parts = [];
  const applied = new Set(q.relaxations ?? []);

  if (q.station) {
    // ⚠️ 緩和を適用したあとは、広げたあとの数字を言う。元の20分のまま
    //    「20分以内で3校」と書くと、実際には25分の学校が並んでいて嘘になる。
    const limit = (q.commute_limit ?? 60) + (applied.has("commute_15") ? 15 : 0);
    parts.push(q.no_commute_limit ? `${q.station}駅から` : `${q.station}駅から${limit}分以内`);
  }
  if (q.wants?.clubs?.length) {
    parts.push(applied.has("club_similar")
      ? `${q.wants.clubs.join("・")}と似た種目のある学校`
      : `${q.wants.clubs.join("・")}のある学校`);
  }
  if (q.wants?.course_types?.length) {
    parts.push(`${q.wants.course_types.join("・")}も含めて`);
  }
  if (q.wants?.dept) parts.push(`学科は「${q.wants.dept}」`);
  if (q.wants?.academic) parts.push("大学進学に力を入れている学校");

  if (student?.score != null) {
    parts.push(student.rough
      ? `お子さんの成績（換算内申${student.kansan}・概算）`
      : `お子さんの成績（換算内申${student.kansan}）`);
  }
  return parts.join("、");
}

/** 学校1校ぶんの説明。レコードにある値だけを使う。 */
export function explainSchool(s) {
  const bits = [];

  const where = s.ward ? `${s.ward}にある学校で` : "";
  if (s.commute_minutes != null) {
    bits.push(`${s.name}は${where}、通学はおよそ${s.commute_minutes}分です`);
  } else {
    bits.push(`${s.name}は${where}、通学時間のデータがありません`);
  }

  if (s.tier_label) {
    const gap = s.score_gap == null ? "" : `（目安点との差 ${s.score_gap > 0 ? "+" : ""}${s.score_gap}点）`;
    bits.push(`合格の見込みは${s.tier_label}${gap}`);
  } else if (s.tier_reason) {
    bits.push(s.tier_reason);
  }

  if (s.matched_clubs?.length) bits.push(`希望の${s.matched_clubs.join("・")}があります`);
  if (s.designation) bits.push(`${s.designation}に指定されています`);
  if (s.encourage) {
    bits.push("学力検査によらない選抜のため、点数では判定していませんが候補に残しています");
  }
  if (s.suggested_course) {
    bits.push("ものづくり系をお探しなので、5年制の高専も挙げています");
  }
  if (s.requested_course) {
    if (s.course_types === "高専") {
      bits.push("ご希望の高専です");
    } else if ((s.course_types ?? "").includes("全日制")) {
      // 併設校。全日制の学校として出しているのではないことを、はっきり書く
      bits.push("全日制と定時制の両方がある学校で、ご希望の定時制課程があります");
    } else {
      bits.push("ご希望の定時制です");
    }
  }
  if (s.selection_note) bits.push(s.selection_note);

  return bits.join("。") + "。";
}

/** 全体のまとめ。件数・条件・注意書き。 */
export function explainTemplate(q, payload) {
  const { student, schools = [], count = 0, mode } = payload;
  const cond = conditionText(q, student);
  const lines = [];

  if (count === 0) {
    lines.push(`${cond}で探しましたが、条件をすべて満たす学校は見つかりませんでした。`);
    return lines.join("");
  }

  lines.push(`${cond}で、${count}校が見つかりました。`);

  // 何を広げた結果なのかを必ず言う。黙って条件を外さない（仕様書§5.3）
  const relaxNote = {
    commute_15: "通学時間",
    club_similar: "部活の種目",
    score_range: "合格の目安点の幅",
  };
  const widened = (q.relaxations ?? []).map((k) => relaxNote[k]).filter(Boolean);
  if (widened.length) lines.push(`${widened.join("と")}を広げてお探ししたものです。`);

  if (mode === "commute_only") {
    lines.push("成績の入力がないため、合格の見込みは判定せず、通学の近い順にご案内しています。");
  } else if (student?.rough) {
    lines.push("成績が概算のため、合格の見込みは幅を広めに取っています。");
  }

  const tiers = schools.reduce((acc, s) => {
    if (s.tier_label) acc[s.tier_label] = (acc[s.tier_label] ?? 0) + 1;
    return acc;
  }, {});
  const tierText = Object.entries(tiers).map(([k, v]) => `${k}${v}校`).join("・");
  if (tierText) lines.push(`内訳は${tierText}です。`);

  return lines.join("");
}

/* ------------------------------------------------------------------ */
/* LLM。使えないときは黙って定型文のまま                                */
/* ------------------------------------------------------------------ */

const SYSTEM = `あなたは都立高校の進路相談で、検索結果を保護者に説明する係です。
次の規則を厳密に守ってください。

1. **渡されたJSONに書かれている値だけを使う。** 学校の評判・雰囲気・校風・
   進学実績・部活の強さなど、JSONに無いことは一文字も書かない。
2. 数値は渡された数値をそのまま使う。計算し直さない。丸めない。
3. 合格を保証する言い方をしない。「受かります」「確実です」と書かない。
4. 保護者に向けた敬体で、全体で200字以内。
5. お子さんの性別・家庭状況を推測しない。
6. 出力は説明の文章だけ。前置きも箇条書きの記号も付けない。`;

async function callLLM(env, payloadForLLM) {
  const model = env.AI_MODEL || "@cf/qwen/qwen3-30b-a3b-fp8";
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await env.AI.run(model, {
        messages: [
          { role: "system", content: SYSTEM },
          {
            role: "user",
            content: attempt === 1
              ? JSON.stringify(payloadForLLM)
              : `${JSON.stringify(payloadForLLM)}\n\n（前回は規則に反していました。JSONの値だけを使い、200字以内の文章だけを返してください）`,
          },
        ],
        max_tokens: 400,
      });
      const text = (typeof res === "string" ? res : res?.response ?? "").trim();
      if (text && text.length <= 600) return { ok: true, text, attempts: attempt };
    } catch {
      // 次の試行へ。2回目も駄目なら定型文に落ちる
    }
  }
  return { ok: false, attempts: 2 };
}

/**
 * 検索結果の説明を作る。
 *
 * @returns {{text:string, per_school:object[], source:string, llm_attempts:number}}
 */
export async function explainResults(env, q, payload, { allowLLM = true } = {}) {
  const per_school = (payload.schools ?? []).map((s) => ({
    school_number: s.school_number,
    name: s.name,
    text: explainSchool(s),
  }));
  const template = explainTemplate(q, payload);

  if (!allowLLM || !env?.AI) {
    return {
      text: template,
      per_school,
      source: allowLLM ? "template(ai_unavailable)" : "template(budget_exhausted)",
      llm_attempts: 0,
    };
  }

  // LLMに渡すのは、説明に使ってよい値だけ。余計な内部値は見せない
  const forLLM = {
    条件: conditionText(q, payload.student),
    件数: payload.count,
    成績判定: payload.mode === "commute_only" ? "なし（通学時間順）" : "あり",
    概算: Boolean(payload.student?.rough),
    学校: (payload.schools ?? []).map((s) => ({
      名前: s.name,
      所在地: s.ward,
      通学分: s.commute_minutes,
      合格の見込み: s.tier_label,
      目安点との差: s.score_gap,
      一致した部活: s.matched_clubs,
      指定: s.designation,
      注意書き: s.selection_note,
    })),
  };

  const llm = await callLLM(env, forLLM);
  return {
    text: llm.ok ? llm.text : template,
    per_school,
    source: llm.ok ? "llm" : "template(llm_failed)",
    llm_attempts: llm.attempts,
  };
}
