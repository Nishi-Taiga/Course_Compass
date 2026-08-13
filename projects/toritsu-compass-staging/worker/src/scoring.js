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
  sonaiToKansan: 13 / 9,     // 素内申9教科 → 換算内申
  esatDefault: 12,           // ESAT-J（満点20）の既定値
  max: 1020,
};

/**
 * 推定点と目安点の差分をゾーンに割る閾値。
 * safeMax を超える＝余裕がありすぎる学校は候補から外す（提案する意味がないため）。
 */
export const GAP = { safe: 60, fit: -60, chal: -160, safeMax: 220 };

/**
 * 当日点が概算のとき（内申だけ入力された場合）に使う、広めの閾値。
 * 推定の粒度が粗いぶん、断定を避けて幅を持たせる。
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
};

/**
 * 生徒の推定点を出す。
 *
 * 内申だけでも判定できるようにする（当日点は多くの家庭がまだ持っていないため）。
 * その場合は概算フラグを立て、判定幅を GAP_ROUGH に切り替える。
 *
 * @returns {{score:number|null, rough:boolean, reason:string}}
 */
export function estimateScore({ naishin = null, toujitsu = null, sonai = null, esat = null }) {
  // 素内申（9教科45点満点）しか無ければ換算内申に直す
  let kansan = naishin;
  if (kansan == null && sonai != null) {
    kansan = Math.round(sonai * SCALE.sonaiToKansan);
  }

  if (kansan == null) {
    return {
      score: null,
      rough: false,
      reason: naishin == null && sonai == null
        ? "内申が未入力のため点数判定はしません（通学時間順で提案します）"
        : "入力が不足しています",
    };
  }

  let exam = toujitsu;
  let rough = false;
  if (exam == null) {
    // 内申だけ → 当日点を粗く推定する。内申どおりの当日点より少し辛めに見る
    exam = Math.round((kansan / 65) * 500 * 0.95);
    rough = true;
  }

  const score = Math.round(
    exam * SCALE.exam +
      kansan * SCALE.naishinToScore +
      (esat == null ? SCALE.esatDefault : esat)
  );

  return {
    score,
    rough,
    reason: rough
      ? "内申から当日点を概算しています。判定の幅を広めに取っています"
      : "内申と当日点の両方から算出しています",
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
