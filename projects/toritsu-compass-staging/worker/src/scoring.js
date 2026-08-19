/**
 * 合否判定モデル（1020点の差分方式）
 *
 * ⚠️ このファイルが閾値の唯一の置き場所。値を変えるときはここだけを直す。
 *    レベル帯（1〜5の離散値）は廃止した。帯だと境界（内申39と40）で丸ごと
 *    1段ずれるうえ、帯ごとの校数を人手で均す必要があった。差分方式なら
 *    閾値1箇所の調整で済む。
 *
 * 満点1020 = 当日点500 × 1.4 + 換算内申65 × (300/65) + ESAT-J 20
 */

/** 素点をスケールに乗せる係数。 */
export const SCALE = {
  exam: 1.4,                 // 当日点500点 → 700点
  naishinToScore: 300 / 65,  // 換算内申65 → 300点
  jitsugiWeight: 2,          // 実技4教科は2倍して数える（都立の換算内申の決まり）
  sonaiToKansan: 13 / 9,     // 素内申9教科 → 換算内申（内訳が不明なときの概算）
  esatDefault: 12,           // ESAT-J（満点20）の既定値
  max: 1020,
};

/** 範囲を外れたときに、どの項目かを日本語で伝えるための名前。 */
export const LABEL = {
  naishin5: "5教科の内申の合計",
  jitsugi: "実技4教科の内申の合計",
  naishin: "換算内申",
  sonai: "9教科の内申の合計",
  toujitsu: "当日点",
  esat: "ESAT-J",
};

/** 入力として認める範囲。外れたら黙って丸めず、無効として扱う。 */
export const RANGE = {
  naishin5: [5, 25],   // 5教科（各5点）
  jitsugi: [4, 20],    // 実技4教科（各5点）
  naishin: [9, 65],    // 換算内申
  sonai: [9, 45],      // 素内申9教科の合計
  toujitsu: [0, 500],
  esat: [0, 20],
};

/**
 * 推定点と目安点の差分をゾーンに割る閾値。
 * safeMax を超える＝余裕がありすぎる学校は候補から外す（提案する意味がないため）。
 */
export const GAP = { safe: 60, fit: -60, chal: -160, safeMax: 220 };

/**
 * 推定が概算のときに使う、広めの閾値。粒度が粗いぶん断定を避けて幅を持たせる。
 *
 * 概算になる経路は2つあり、どちらか一方でも当てはまればこちらを使う。
 *   - 当日点が未入力（内申から推定した）
 *   - 内申が9教科の合計しか分からない（実技の内訳が不明）
 * 後者は換算内申が最大7点ずれ、1020点満点では30点を超える。
 */
export const GAP_ROUGH = { safe: 90, fit: -90, chal: -210, safeMax: 280 };

/** 緩和3段目で目安点の判定幅を広げるときの追加分。 */
export const GAP_RELAXED_BONUS = 80;

export const ZONE_LABEL = { s: "安全圏", m: "適正圏", c: "挑戦圏" };

/** 選抜区分ごとの注意書き。表示するだけで、計算式は1本のまま分岐しない。 */
export const SELECTION_LABEL = {
  std: null,
  jiko: "自校作成問題校。共通問題の模試とは尺度がずれます",
  keisha: "傾斜配点があります。得意科目で有利になる場合があります",
  fukasawa: "特別な選抜方式です。募集要項を確認してください",
  ratio64: "当日点と内申の比率が6:4です",
  no_exam: "学力検査なし（面接・作文で選抜）",
  kosen: "高専は入試の方式が都立高校と異なります（学力検査3教科＋調査書）",
};

/** 範囲に収まっていれば数値、外れていれば null。黙って丸めない。 */
function valid(v, key) {
  if (v == null || !Number.isFinite(v)) return null;
  const [lo, hi] = RANGE[key];
  return v >= lo && v <= hi ? v : null;
}

/**
 * 換算内申（65点満点）を出す。
 *
 * 都立の換算内申は 5教科×1 + 実技4教科×2 なので、**9教科の合計45点からは
 * 復元できない**。5教科25・実技8 の生徒なら 25+16=41 が正しいが、
 * ×13/9 の概算では48と出る。1020点満点に直すと約33点のずれで、
 * 安全圏のしきい値60点の半分を超える＝判定が1ランク変わる大きさ。
 *
 * そのため入力は次の優先順で見る。概算経路は残す（空振りさせないため）。
 *   1. naishin      … 換算内申そのもの
 *   2. naishin5 + jitsugi … 内訳から厳密に算出
 *   3. sonai        … 9教科合計しか分からない場合の概算（rough を立てる）
 *
 * @returns {{kansan:number|null, rough:boolean, basis:string}}
 */
export function toKansan({ naishin = null, naishin5 = null, jitsugi = null, sonai = null }) {
  const n = valid(naishin, "naishin");
  if (n != null) return { kansan: n, rough: false, basis: "換算内申の直接入力" };

  const n5 = valid(naishin5, "naishin5");
  const j4 = valid(jitsugi, "jitsugi");
  if (n5 != null && j4 != null) {
    return {
      kansan: n5 + j4 * SCALE.jitsugiWeight,
      rough: false,
      basis: `5教科${n5} ＋ 実技${j4}×${SCALE.jitsugiWeight}`,
    };
  }

  const s = valid(sonai, "sonai");
  if (s != null) {
    // 実技の内訳が分からないと換算内申は最大7点ほどぶれる。概算として扱う
    return {
      kansan: Math.round(s * SCALE.sonaiToKansan),
      rough: true,
      basis: `9教科合計${s}からの概算`,
    };
  }

  // 5教科だけ、実技だけ、では換算内申を出せない。片方だけの入力は無効とする
  return { kansan: null, rough: false, basis: "" };
}

/**
 * 生徒の推定点を出す。
 *
 * 内申だけでも判定できるようにする（当日点は多くの家庭がまだ持っていないため）。
 * 概算の経路を通ったときは rough を立て、判定幅を GAP_ROUGH に切り替える。
 * 概算になる理由は2つあり（当日点の推定 / 内申の内訳不明）、独立に起こる。
 * 当日点があっても内申が9教科合計だけ、という組み合わせがあるため。
 *
 * @returns {{score:number|null, rough:boolean, exam_rough:boolean,
 *            naishin_rough:boolean, kansan:number|null, reason:string}}
 */
export function estimateScore(input) {
  const { toujitsu = null, esat = null } = input;
  const { kansan, rough: naishinRough, basis } = toKansan(input);

  // 入力されているのに範囲外の項目。黙って捨てると、なぜ判定が変わったのかが
  // 利用者に分からなくなる。呼び出し側が聞き直せるように名前で返す。
  const invalid = Object.keys(RANGE).filter(
    (k) => input[k] != null && valid(Number(input[k]), k) == null
  );

  if (kansan == null) {
    const partial = input.naishin5 != null || input.jitsugi != null;
    let reason;
    if (invalid.length) {
      reason = invalid.map((k) => `${LABEL[k]}は${RANGE[k][0]}〜${RANGE[k][1]}の範囲で教えてください`).join("。");
    } else if (partial) {
      reason = "内申は5教科と実技4教科の両方が揃うと判定できます";
    } else {
      reason = "内申が未入力のため点数判定はしません（通学時間順で提案します）";
    }
    return {
      score: null,
      rough: false,
      exam_rough: false,
      naishin_rough: false,
      kansan: null,
      invalid,
      reason,
    };
  }

  let exam = valid(toujitsu, "toujitsu");
  const examRough = exam == null;
  if (examRough) {
    // 内申だけ → 当日点を粗く推定する。内申どおりの当日点より少し辛めに見る
    exam = Math.round((kansan / 65) * 500 * 0.95);
  }

  const e = valid(esat, "esat");
  const score = Math.round(
    exam * SCALE.exam + kansan * SCALE.naishinToScore + (e == null ? SCALE.esatDefault : e)
  );

  const why = [];
  if (examRough) why.push("当日点は内申からの推定です");
  if (naishinRough) why.push("内申は9教科の合計からの概算です（実技の内訳が分かると正確になります）");
  if (invalid.length) {
    why.push(`${invalid.map((k) => LABEL[k]).join("・")}は範囲外だったため使っていません`);
  }

  return {
    score,
    rough: examRough || naishinRough,
    exam_rough: examRough,
    naishin_rough: naishinRough,
    kansan,
    invalid,
    reason: why.length
      ? `${why.join("。")}。判定の幅を広めに取っています（換算内申は${basis}）`
      : `内申と当日点の両方から算出しています（換算内申は${basis}）`,
  };
}

/**
 * 学校ひとつのゾーンを判定する。
 *
 * @returns {{tier:string|null, gap:number|null, reason:string}}
 *   tier が null なら「数値では判定しない」。候補から外す意味ではない。
 */
export function tierOf(school, score, rough, relaxed = false) {
  if (school.selection_type === "no_exam") {
    return { tier: null, gap: null, reason: "学力検査がないため点数では判定しません" };
  }
  if (school.target_score == null) {
    // ⚠️「未設定」と書くとデータの不備に見える。**測れない**のではなく
    //    **測り方が違う**ことを伝える（2026-08-19）。
    const course = school.course_types ?? "";
    if (course === "高専") {
      return {
        tier: null, gap: null,
        reason: "高専は入試の方式が異なるため（学力検査3教科＋調査書）、"
              + "都立高校の目安点では判定していません",
      };
    }
    if (course.includes("定時制") && !course.includes("全日制")) {
      return {
        tier: null, gap: null,
        /* ⚠️ 保留中（西・2026-08-19）: 定時制を5教科の目安点で判定しない扱いは
           暫定。塾の実感として妥当か判断待ちで、変えるならここと
           school_scores.csv の定時制の行を見直す。 */
        reason: "定時制は学力検査の教科数が学校ごとに違うため、"
              + "5教科の目安点では判定していません",
      };
    }
    return { tier: null, gap: null, reason: "目安点が未設定です" };
  }
  if (score == null) {
    return { tier: null, gap: null, reason: "成績の入力がないため点数では判定しません" };
  }

  const base = rough ? GAP_ROUGH : GAP;
  const bonus = relaxed ? GAP_RELAXED_BONUS : 0;
  const g = {
    safe: base.safe,
    fit: base.fit - bonus,
    chal: base.chal - bonus,
    safeMax: base.safeMax + bonus,
  };

  const gap = score - school.target_score;

  if (gap > g.safeMax) {
    return { tier: null, gap, reason: "余裕がありすぎるため候補から外しています" };
  }
  if (gap >= g.safe) return { tier: "s", gap, reason: "目安点を上回っています" };
  if (gap >= g.fit) return { tier: "m", gap, reason: "目安点とほぼ同じです" };
  if (gap >= g.chal) return { tier: "c", gap, reason: "目安点をやや下回ります" };

  return { tier: null, gap, reason: "目安点から離れているため候補から外しています" };
}
