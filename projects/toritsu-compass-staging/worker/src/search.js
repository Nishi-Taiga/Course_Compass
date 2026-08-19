/**
 * 検索の中核。プロトタイプ（prototype/index.html）の search() / relax() の移植。
 *
 * ここにLLMは一切関わらない。進行と検索はコードが握る（仕様書§3.1）。
 * LLMを先につなぐと、不具合が検索側なのかLLM側なのか切り分けられなくなるため、
 * まずこれだけで完全に動く状態を作る。
 */

import { estimateScore, toKansan, tierOf, ZONE_LABEL, SELECTION_LABEL } from "./scoring.js";

/** 緩和は必ず段階を踏み、毎回承諾を取る（仕様書§5.3）。黙って条件を外さない。 */
export const RELAXATIONS = [
  {
    key: "commute_15",
    label: "通学時間を15分広げる",
    describe: (q) => `通学 ${q.commute_limit}分以内 → ${q.commute_limit + 15}分以内`,
  },
  {
    key: "club_similar",
    label: "部活を似た種目まで広げる",
    describe: () => "指定された部活と同じカテゴリの部活がある学校も含めます",
  },
  {
    key: "score_range",
    label: "合格の目安点の幅を広げる",
    describe: () => "挑戦圏をもう少し広く取り、届きそうな学校まで含めます",
  },
];

/** 部活の類似カテゴリ。緩和2段目で使う。正規化辞書は西が監修するまでの暫定。 */
export const CLUB_CATEGORIES = {
  球技: ["サッカー", "野球", "バスケットボール", "バレーボール", "テニス", "卓球", "バドミントン", "ハンドボール", "ラグビー"],
  武道: ["柔道", "剣道", "弓道", "空手", "相撲", "なぎなた"],
  音楽: ["吹奏楽", "軽音楽", "音楽", "合唱", "箏曲", "オーケストラ"],
  美術: ["美術", "書道", "写真", "漫画", "デザイン"],
  理科: ["生物", "化学", "物理", "地学", "天文", "科学", "理科"],
};

function similarClubs(name) {
  const hits = new Set([name]);
  for (const members of Object.values(CLUB_CATEGORIES)) {
    if (members.some((m) => name.includes(m))) members.forEach((m) => hits.add(m));
  }
  return [...hits];
}

/**
 * 重視軸による加点（仕様書§5.1の3番）。
 *
 * ⚠️ 仕様書の該当箇所を確認できていないため、プロトタイプの並び（通学時間順）を
 *    土台に、重視軸ごとの加点を足す形で暫定実装している。配点は要レビュー。
 *    透明性のために、何が効いたかを why に必ず積む。
 */
function scoreCandidate(row, q, tier) {
  let score = 0;
  const why = [];

  // 通学は近いほど良い。60分で0点、0分で60点。
  const commute = Math.max(0, 60 - (row.commute_minutes ?? 60));
  score += commute;
  if (row.commute_minutes != null) {
    // 「◯◯駅からバス」まで書く。数字だけより保護者に伝わる
    const via = row.via_station ? `${row.via_station}駅から` : "";
    const leg = row.access_mode === "bus" ? "バス" : "徒歩";
    why.push(`通学${row.commute_minutes}分（${via}${leg}）`);
  }

  // 適正圏を最上位に置く。安全圏ばかり並べても相談の役に立たない。
  if (tier === "m") { score += 40; why.push("適正圏"); }
  else if (tier === "c") { score += 25; why.push("挑戦圏"); }
  else if (tier === "s") { score += 15; why.push("安全圏"); }

  // 配点は 2026-08-19 に指定を受けて更新した。
  //   適正圏 +40 / 学科一致 +40 / 部活一致 +30 / 進学指導指定 +10
  // 挑戦圏(+25)・安全圏(+15)は指定が無かったので据え置き。
  if (q.wants?.academic && row.designation) {
    score += 10;
    why.push(`大学進学重視 → ${row.designation}`);
  }
  if (q.wants?.dept && row.departments?.includes(q.wants.dept)) {
    score += 40;
    why.push(`学科の希望「${q.wants.dept}」に一致`);
  }
  if (row.matched_clubs?.length) {
    score += 30;
    why.push(`希望の部活: ${row.matched_clubs.join("・")}`);
  }

  return { match_score: Math.round(score), why };
}

/**
 * 検索本体。
 *
 * @param {D1Database} db
 * @param {object} q  クエリ（station, commute_limit, no_commute_limit,
 *                       naishin5/jitsugi（内申の内訳）, naishin, sonai, toujitsu,
 *                       esat, wants, relaxations）
 */
export async function searchSchools(db, q) {
  const applied = new Set(q.relaxations ?? []);
  const limit = q.commute_limit + (applied.has("commute_15") ? 15 : 0);

  const student = estimateScore(q);

  // --- 必須フィルタはSQL側で落とす。10万行の結合をJSに持ち込まない ---
  //
  // ⚠️ プレースホルダは **SQL文に現れる順** に束ねること。JOIN句は WHERE句より
  //    前に来るので、部活のバインドは通学時間・学科より先。ひとつの配列に
  //    書いた順で push していくと、JOINとWHEREで値が入れ違う。
  //    （school_clubs が空のうちは部活の ? が増えないため、この取り違えは
  //      データを入れるまで表に出なかった）
  const joinBinds = [];
  const clubBinds = [];
  const whereBinds = [];
  // 既定は全日制だけ。定時制・高専は**希望されたときだけ**足す（2026-08-19 決定）。
  // 黙って混ぜると、普通に探している保護者に点数判定できない学校が並んでしまう。
  const wantCourses = q.wants?.course_types ?? [];
  const courseConds = ["s.course_types LIKE '%全日制%'"];
  if (wantCourses.includes("定時制")) courseConds.push("s.course_types LIKE '%定時制%'");
  if (wantCourses.includes("高専")) courseConds.push("s.course_types = '高専'");

  const where = [
    "s.no_hs_admission = 0",            // 高校からの募集停止（中高一貫5校）は出さない
    `(${courseConds.join(" OR ")})`,
  ];

  let commuteJoin = "LEFT JOIN commute_times c ON c.school_number = s.school_number AND c.from_station = ?";
  joinBinds.push(q.station);

  if (!q.no_commute_limit) {
    where.push("c.minutes IS NOT NULL");
    where.push("c.minutes <= ?");
    whereBinds.push(limit);
  }

  if (q.wants?.dept) {
    where.push("s.departments LIKE ?");
    whereBinds.push(`%${q.wants.dept}%`);
  }

  // 部活フィルタ。raw_name はサイトの表記のままなので、部分一致で当てる
  // （「吹奏楽」で「吹奏楽部」に当たる）。正規化は西の監修後に normalized で行う。
  const wantClubs = q.wants?.clubs ?? [];
  let clubJoin = "";
  if (wantClubs.length) {
    const names = applied.has("club_similar")
      ? [...new Set(wantClubs.flatMap(similarClubs))]
      : wantClubs;
    const conds = names.map(() => "cl.raw_name LIKE ?").join(" OR ");
    names.forEach((n) => clubBinds.push(`%${n}%`));
    clubJoin = `LEFT JOIN school_clubs cl ON cl.school_number = s.school_number AND (${conds})`;
  }

  const sql = `
    SELECT s.school_number, s.name, s.ward, s.departments, s.designation, s.course_types,
           s.target_score, s.selection_type, s.selection_note, s.score_layer,
           s.source_master, s.source_designation, s.source_target_score,
           c.minutes AS commute_minutes, c.via_station, c.access_mode
           ${wantClubs.length ? ", GROUP_CONCAT(DISTINCT cl.raw_name) AS matched_clubs_csv" : ""}
      FROM schools s
      ${commuteJoin}
      ${clubJoin}
     WHERE ${where.join(" AND ")}
     ${wantClubs.length ? "GROUP BY s.school_number" : ""}
     ORDER BY c.minutes IS NULL, c.minutes`;

  const binds = [...joinBinds, ...clubBinds, ...whereBinds];   // SQL文に現れる順
  const { results } = await db.prepare(sql).bind(...binds).all();

  const rows = results.map((r) => ({
    ...r,
    matched_clubs: r.matched_clubs_csv ? r.matched_clubs_csv.split(",") : [],
  }));

  // 部活が指定されていて緩和前なら、実際に一致した学校だけに絞る。
  //
  // ⚠️ 以前は「一致0件なら絞らない」という逃げを入れていた（school_clubs が
  //    空のうちは全校が0件になるため）。データが入った今それを残すと、
  //    無い部活を指定したときに黙って条件を外した結果を返してしまう。
  //    0件は0件として返し、緩和を提案する（仕様書§5.3）。
  if (wantClubs.length && !applied.has("club_similar")) {
    for (let i = rows.length - 1; i >= 0; i--) {
      if (!rows[i].matched_clubs.length) rows.splice(i, 1);
    }
  }

  // --- ゾーン判定 ---
  const relaxedScore = applied.has("score_range");
  const judged = rows.map((r) => {
    const t = tierOf(r, student.score, student.rough, relaxedScore);
    return { ...r, tier: t.tier, score_gap: t.gap, tier_reason: t.reason };
  });

  // --- 成績なしの経路。0件にせず通学時間順で返す（仕様書§5.2） ---
  if (student.score == null) {
    const picked = judged.slice(0, 4);
    return { student, rows: decorate(picked, q), all: judged, mode: "commute_only" };
  }

  const pool = judged.filter((r) => r.tier);
  const pick = (t, n) => pool.filter((r) => r.tier === t).slice(0, n);
  let out = [
    ...pick("c", q.wants?.academic ? 2 : 1),
    ...pick("m", 2),
    ...pick("s", 1),
  ];
  if (!out.length) out = pool.slice(0, 4);

  // 学力検査によらない学校（エンカレッジ）は点数で切らない。
  // 成績に不安がある相談ほど価値のある選択肢なので、圏外にせず必ず1校添える。
  const encourage = judged.find((r) => r.selection_type === "no_exam");
  const noSafe = !out.some((r) => r.tier === "s");
  if (encourage && !out.some((r) => r.school_number === encourage.school_number)
      && (student.rough || noSafe || pool.length < 3)) {
    out.push({ ...encourage, encourage: true });
  }

  // 希望された課程（定時制・高専）は、目安点が無いので tier が付かず pool に
  // 入らない。そのままだと「定時制も見たい」と言われたのに1校も出ない。
  // 通学の近い順に最大2校、明示的に足す。
  if (wantCourses.length) {
    const extra = judged
      .filter((r) => !out.some((o) => o.school_number === r.school_number))
      .filter((r) => wantCourses.some((c) => (r.course_types ?? "").includes(c)))
      .slice(0, 2);
    out.push(...extra.map((r) => ({ ...r, requested_course: true })));
  }

  return { student, rows: decorate(out, q), all: judged, mode: "scored" };
}

function decorate(rows, q) {
  return rows.map((r) => {
    const { match_score, why } = scoreCandidate(r, q, r.tier);
    return {
      school_number: r.school_number,
      name: r.name,
      ward: r.ward,
      departments: r.departments,
      designation: r.designation,
      commute_minutes: r.commute_minutes,
      commute_range: r.commute_minutes == null ? null : rangeText(r.commute_minutes),
      tier: r.tier,
      tier_label: r.tier ? ZONE_LABEL[r.tier] : null,
      tier_reason: r.tier_reason,
      score_gap: r.score_gap,
      target_score: r.target_score,
      selection_type: r.selection_type,
      selection_note: r.selection_note || SELECTION_LABEL[r.selection_type] || null,
      score_layer: r.score_layer,
      encourage: r.encourage ?? false,
      course_types: r.course_types,
      // 「定時制も見たい」等の希望に応えて足した学校であることを画面に出せるように
      requested_course: r.requested_course ?? false,
      matched_clubs: r.matched_clubs ?? [],
      match_score,
      why,
      // 出典を各レコードに載せる。「この数字は都教委の公開資料由来」が
      // 画面まで届かないと、審査では実装していないのと同じになる。
      sources: {
        master: r.source_master,
        designation: r.source_designation,
        target_score: r.source_target_score,
        commute: "駅間所要時間の自前計算（station_database CC BY-SA 4.0 / 急行補正済）",
      },
    };
  }).sort((a, b) => b.match_score - a.match_score);
}

const rangeText = (m) => {
  const lo = Math.max(5, Math.floor(m / 15) * 15);
  return `${lo}〜${lo + 15}分`;
};

/**
 * 0件だったときの緩和提案。何を緩めるかを必ず明示する。
 * 黙って条件を外さない誠実さが、デモで一番語れる部分（仕様書§5.3）。
 */
export function buildRelaxation(q) {
  const applied = new Set(q.relaxations ?? []);
  const next = RELAXATIONS.filter((r) => {
    if (applied.has(r.key)) return false;
    if (r.key === "club_similar" && !(q.wants?.clubs ?? []).length) return false;
    // 目安点の幅を広げる緩和は、点数判定ができているときにだけ意味がある
    if (r.key === "score_range" && toKansan(q).kansan == null) return false;
    return true;
  });

  if (!next.length) {
    return {
      message: "条件をすべて広げましたが、該当する学校が見つかりませんでした。"
        + "出発駅か通学時間を変えて、もう一度お試しください。",
      options: [],
      exhausted: true,
    };
  }

  return {
    message: "申し訳ありません、すべての条件を満たす学校が見つかりませんでした。"
      + "次のいずれかを広げると見つかる可能性があります。どれを広げますか？",
    options: next.map((r) => ({
      key: r.key,
      label: r.label,
      change: r.describe(q),
    })),
    already_relaxed: [...applied],
    exhausted: false,
  };
}
