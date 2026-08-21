/**
 * 検索条件のスキーマ。ここが唯一の定義。
 *
 * 同じ定義を3つの用途で使い回す（2026-08-13 MTG決定の受け入れ基準に対応）。
 *   1. POST /api/search の入力検証
 *   2. LLMが抽出した条件の検証
 *   3. 「何が埋まっていないか」の判定 ＝ 聞き返す項目の決定
 *
 * ⚠️ 3番が肝。**何が足りないかはコードが決める。** LLMには判定させない。
 *    LLMが不調でも聞き返しのループが壊れないようにするため（仕様書§3.1の
 *    「進行はコードが握る」をそのまま実装したもの）。LLMに任せるのは、
 *    足りない項目を日本語でどう尋ねるかだけ。
 */

import { RANGE, LABEL, toKansan } from "./scoring.js";

const num = (v) => (v == null || v === "" ? null : Number(v));

/** 全日制のほかに検索へ含められる課程。schools.course_types の値と揃える。 */
export const COURSE_TYPES = ["定時制", "高専"];

/**
 * 学校選びで何をいちばん大事にするか（仕様書§5.1の「重視軸」）。
 *
 * ⚠️ 部活・学科は検索の絞り込みでも効いている。「吹奏楽部がある学校」で
 *    絞ったうえで部活を重視と言われても、候補は全員が該当するので
 *    加点しただけでは順位が動かない。効くのは次の2つの場合。
 *      - 緩和で似た種目まで広げたとき（完全一致の学校を上に戻す）
 *      - 部活を複数挙げたとき（多く当てはまる学校を上に）
 *    それでも選択肢として並べるのは、保護者が「部活がいちばん大事」と
 *    言えないほうが不自然なため（2026-08-21 決定）。
 */
export const PRIORITIES = {
  commute: "通学の近さ",
  academic: "大学進学",
  club: "入りたい部活",
  dept: "学びたい学科",
  reachable: "いま届きそうなところ",
};

/**
 * 生のリクエストボディを検索条件に整える。
 * 範囲外の値は黙って丸めず、invalid に名前を残して null にする。
 */
export function parseQuery(body = {}) {
  const invalid = [];
  const pick = (key) => {
    const v = num(body[key]);
    if (v == null) return null;
    if (!Number.isFinite(v)) { invalid.push(key); return null; }
    const [lo, hi] = RANGE[key];
    if (v < lo || v > hi) { invalid.push(key); return null; }
    return v;
  };

  const commute = num(body.commute_limit);
  const q = {
    // 文字数の上限は乱打・巨大SQL対策。正常な入力はこの範囲に収まる
    station: String(body.station ?? "").trim().slice(0, 30),
    // 未指定は null のまま返す。60を既定で入れてしまうと、本人が言ったのか
    // こちらが決めたのかが区別できず、「通学時間は？」を何度も聞くことになる。
    // 検索時の既定60分は handleSearch が入れる。
    commute_limit: Number.isFinite(commute) && commute > 0 ? commute : null,
    no_commute_limit: Boolean(body.no_commute_limit),

    naishin: pick("naishin"),
    naishin5: pick("naishin5"),
    jitsugi: pick("jitsugi"),
    sonai: pick("sonai"),
    toujitsu: pick("toujitsu"),
    esat: pick("esat"),

    wants: {
      // いちばん大事にしたいこと。1つだけ選ぶ（複数を重視は「重視なし」と同じ）
      priority: body.wants?.priority in PRIORITIES ? body.wants.priority : null,
      academic: Boolean(body.wants?.academic) || body.wants?.priority === "academic",
      // 希望された課程。既定（空）は全日制だけを見る。
      // 「定時制も見たい」「高専に興味がある」と言われたときだけ広げる
      // （2026-08-19 決定。黙って混ぜると、普通に探している保護者に
      //   点数判定できない学校が並んで分かりにくくなる）
      course_types: Array.isArray(body.wants?.course_types)
        ? body.wants.course_types.filter((c) => COURSE_TYPES.includes(c))
        : [],
      dept: body.wants?.dept ? String(body.wants.dept).slice(0, 30) : null,
      clubs: Array.isArray(body.wants?.clubs)
        ? body.wants.clubs.filter(Boolean).slice(0, 5).map((c) => String(c).slice(0, 30))
        : [],
    },
    relaxations: Array.isArray(body.relaxations) ? body.relaxations : [],
    // 抽出しきれなかった発話をそのまま持ち回る（仕様書§4.3）。
    // 取りこぼした部分を後から見返せるようにするため、捨てない。
    free_text: Array.isArray(body.free_text)
      ? body.free_text.filter(Boolean).slice(-10).map((t) => String(t).slice(0, 500))
      : [],
  };

  return { q, invalid };
}

/**
 * 聞く順序。上から順に、埋まっていない最初のものを尋ねる。
 *
 * `declined` に入っている項目は二度と聞かない。「わからない」と答えたことを
 * 覚えないと同じ質問を繰り返すことになり、保護者が離脱する。
 */
export const SLOTS = [
  {
    key: "station",
    label: "最寄り駅",
    required: true,
    filled: (q) => Boolean(q.station),
    question: "お住まいの最寄り駅を教えてください。そこからの通学時間で絞り込みます。",
  },
  {
    key: "commute_limit",
    label: "通学時間の上限",
    required: false,
    // 既定60分で検索はできるが、一度は本人に確かめる
    filled: (q, asked) => q.commute_limit != null || asked.has("commute_limit"),
    question: "通学時間はどのくらいまでなら通えそうですか。（例: 45分以内）",
  },
  {
    key: "naishin",
    label: "内申",
    required: false,
    filled: (q) => toKansan(q).kansan != null,
    question:
      "通知表の内申を教えてください。都立は5教科と実技4教科で重みが違うので、"
      + "まず5教科の合計（25点満点）をお願いします。"
      + "手元に無ければ「わからない」で構いません。通学時間順でお探しします。",
    // 5教科だけ入っている途中の状態では、続きを聞く
    partial: (q) =>
      (q.naishin5 != null && q.jitsugi == null)
        ? "実技4教科（音楽・美術・保健体育・技術家庭）の合計も教えてください。20点満点です。"
        : (q.jitsugi != null && q.naishin5 == null)
          ? "5教科（国語・数学・英語・社会・理科）の合計も教えてください。25点満点です。"
          : null,
  },
  {
    key: "wants",
    label: "重視すること",
    required: false,
    filled: (q, asked) =>
      asked.has("wants") || q.wants.priority != null || q.wants.academic
      || q.wants.dept != null || q.wants.clubs.length > 0,
    // 例示は PRIORITIES と揃える。ここに挙げたものだけが軸として受け取れる。
    question:
      "学校選びで、いちばん大事にしたいことはどれですか。"
      + "（通学の近さ / 大学進学 / 入りたい部活 / 学びたい学科 / "
      + "いま届きそうなところ / 特にない）",
  },
];

/**
 * いまの条件を点検して、検索できるか・次に何を聞くかを返す。
 *
 * @param {object} q       parseQuery の結果
 * @param {string[]} asked すでに尋ねた項目
 * @param {string[]} declined 「わからない」と言われた項目
 */
export function inspect(q, asked = [], declined = []) {
  const askedSet = new Set(asked);
  const declinedSet = new Set(declined);

  const filled = [];
  const pending = [];
  for (const slot of SLOTS) {
    if (slot.filled(q, askedSet)) { filled.push(slot.key); continue; }
    if (declinedSet.has(slot.key)) continue;   // 聞き済みで「わからない」
    pending.push(slot);
  }

  const missingRequired = SLOTS
    .filter((s) => s.required && !s.filled(q, askedSet))
    .map((s) => s.key);

  // 途中まで埋まっている項目（5教科だけ入力された等）は最優先で続きを聞く
  const partialSlot = SLOTS.find((s) => s.partial && s.partial(q));
  const next = partialSlot ?? pending[0] ?? null;
  const question = partialSlot
    ? partialSlot.partial(q)
    : next
      ? next.question
      // 聞くことが無くなったら黙らずに、次に何が起きるかを伝える
      : (missingRequired.length === 0
          ? "うかがった条件でお探しします。少しお待ちください。"
          : null);

  return {
    searchable: missingRequired.length === 0,
    missing_required: missingRequired,
    filled,
    pending: pending.map((s) => s.key),
    next: next ? next.key : null,
    question,
  };
}

/** 範囲外だった項目を、そのまま画面や発話に出せる日本語にする。 */
export function invalidMessages(invalid = []) {
  return invalid.map((k) => `${LABEL[k] ?? k}は${RANGE[k][0]}〜${RANGE[k][1]}の範囲で教えてください`);
}
