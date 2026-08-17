/**
 * 緩和の往復。「どれを広げますか？」への返事を読む。
 *
 * 仕様書§5.3 は緩和について「**毎回承諾を取る**」「黙って条件を外さない」と
 * 定めている。検索側（search.js の buildRelaxation）は0件のときに選択肢を
 * 返すところまでできていたが、**その返事を受ける口が会話側に無かった**ため、
 * 承諾を取りようがなかった。ここがその受け口。
 *
 * ⚠️ 段階を踏む。一度に複数の条件を広げない。返事1回につき1つだけ適用する。
 *    まとめて広げると、何が効いて見つかったのかが利用者にも我々にも分からなくなる。
 */

/** 選択肢ごとの手がかり。label と重ならない言い方も拾う。 */
const HINTS = {
  commute_15: /通学|時間|分|遠く|距離|範囲/,
  club_similar: /部活|クラブ|似た|近い種目|種目/,
  score_range: /点|成績|目安|レベル|学力|偏差/,
};

const YES_RE = /はい|うん|お願い|それで|そうし|いいです|やって|広げて/;

// ⚠️「大丈夫です」は断りの意味で使われる。承諾側に入れると、断ったのに
//    条件を広げてしまう。「いえ」も「いいえ」とは別に拾う必要がある。
const NO_RE = /いいえ|^いえ|いや|やめ|結構|大丈夫|しない|変えない|そのまま|いらない|このまま/;

/**
 * 緩和の提案に対する返事を読む。
 *
 * @param {string} text     利用者の発話
 * @param {string[]} offered 直前に提示した緩和のキー
 * @returns {{key:string|null, declined:boolean, ambiguous:boolean}}
 */
export function interpretRelaxation(text, offered = []) {
  const s = String(text ?? "").trim();
  if (!s || !offered.length) return { key: null, declined: false, ambiguous: false };

  if (NO_RE.test(s)) return { key: null, declined: true, ambiguous: false };

  // 「1番」「2」のような番号での指定
  const num = s.match(/^([1-9１-９])\s*(?:番|つ目|つめ)?[。.]?$/);
  if (num) {
    const idx = Number(num[1].replace(/[１-９]/, (c) => String(c.charCodeAt(0) - 0xfee0))) - 1;
    if (idx >= 0 && idx < offered.length) {
      return { key: offered[idx], declined: false, ambiguous: false };
    }
  }

  // 言葉での指定。複数当たったら決め打ちせず聞き直す
  const hits = offered.filter((key) => HINTS[key]?.test(s));
  if (hits.length === 1) return { key: hits[0], declined: false, ambiguous: false };
  if (hits.length > 1) return { key: null, declined: false, ambiguous: true };

  // 「はい」だけ。選択肢が1つならそれ、複数ならどれか聞く
  if (YES_RE.test(s)) {
    if (offered.length === 1) return { key: offered[0], declined: false, ambiguous: false };
    return { key: null, declined: false, ambiguous: true };
  }

  return { key: null, declined: false, ambiguous: false };
}

/** 承諾を受けたときに返す言葉。何を広げたかを必ず言う（黙って外さないため）。 */
export function acceptedMessage(key, q) {
  switch (key) {
    case "commute_15":
      return `通学時間を ${q.commute_limit ?? 60}分以内から ${(q.commute_limit ?? 60) + 15}分以内に広げて、もう一度お探しします。`;
    case "club_similar":
      return "希望の部活と同じカテゴリの部活がある学校まで広げて、もう一度お探しします。";
    case "score_range":
      return "合格の目安点の幅を広げ、届きそうな学校まで含めてお探しします。";
    default:
      return "条件を広げて、もう一度お探しします。";
  }
}

/** どれを広げるか決めきれないときに聞き返す言葉。 */
export function chooseMessage(offered, labels) {
  const list = offered.map((k, i) => `${i + 1}. ${labels[k] ?? k}`).join(" / ");
  return `どれを広げましょうか。${list}`;
}

/** 断られたときの言葉。条件を変える方向へ促す。 */
export const DECLINED_MESSAGE =
  "承知しました。条件はそのままにします。出発駅や通学時間を変えると見つかるかもしれません。";

/** キー → 表示名。search.js の RELAXATIONS と揃える。 */
export const RELAX_LABELS = {
  commute_15: "通学時間を15分広げる",
  club_similar: "部活を似た種目まで広げる",
  score_range: "合格の目安点の幅を広げる",
};
