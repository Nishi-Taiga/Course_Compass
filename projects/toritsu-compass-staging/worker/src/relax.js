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

// はっきり承諾。これらは他の語より先に見る（「それでいいです」を
// 曖昧扱いにしないため）。
const YES_RE = /はい|うん|お願い|それで|そうし|やって|広げて/;

// はっきり断り。
// ⚠️「広げなくていいです」のような否定形も拾う。「いいです」を含むので、
//    先に断りとして判定しないと曖昧語（UNCLEAR_RE）に流れてしまう。
const NO_RE =
  /いいえ|^いえ|いや|やめ|結構|しない|変えない|そのまま|いらない|このまま|なくてい|なくても|ないで|なしで|不要/;

// ⚠️ どちらとも取れる言葉。**決めずに聞き返す。**
//    「大丈夫です」「いいです」は日本語では承諾にも断りにもなる。
//    §5.3が「毎回承諾を取る」と定めている以上、ここで推測して条件を
//    広げてはいけない（黙って条件を外すのと同じことになる）。
//    断り側に倒す手もあるが、それだと承諾したのに何も起きない体験になる。
const UNCLEAR_RE = /大丈夫|いいです|いいよ|まあ|どちらでも|お任せ/;

/**
 * 緩和の提案に対する返事を読む。
 *
 * @param {string} text     利用者の発話
 * @param {string[]} offered 直前に提示した緩和のキー
 * @returns {{key:string|null, declined:boolean, ambiguous:boolean}}
 */
export function interpretRelaxation(text, offered = []) {
  const s = String(text ?? "").trim();
  const none = { key: null, declined: false, ambiguous: false, kind: null };
  if (!s || !offered.length) return none;

  if (NO_RE.test(s)) return { ...none, declined: true };

  // はっきりした承諾・番号・種目の指定より先に、曖昧語だけの返事を捕まえる。
  // ただし「それでいいです」のように承諾の語を含むものは承諾として扱う。
  if (UNCLEAR_RE.test(s) && !YES_RE.test(s) && !/[1-9１-９]/.test(s)
      && !Object.values(HINTS).some((re) => re.test(s))) {
    return { ...none, ambiguous: true, kind: "yesno" };
  }

  // 「1番」「2」「2番でお願いします」のような番号での指定。
  // ⚠️ 数字だけの返事は全体が数字のときに限る。後ろに文が続く場合は
  //    「番」「つ目」が必要（「15分広げて」の先頭の1を選択肢1と読まないため）。
  const num = s.match(/^([1-9１-９])\s*[。.]?$/)
    ?? s.match(/([1-9１-９])\s*(?:番|つ目|つめ)/);
  if (num) {
    const idx = Number(num[1].replace(/[１-９]/, (c) => String(c.charCodeAt(0) - 0xfee0))) - 1;
    if (idx >= 0 && idx < offered.length) {
      return { ...none, key: offered[idx] };
    }
  }

  // 言葉での指定。複数当たったら決め打ちせず聞き直す
  const hits = offered.filter((key) => HINTS[key]?.test(s));
  if (hits.length === 1) return { ...none, key: hits[0] };
  if (hits.length > 1) return { ...none, ambiguous: true, kind: "which" };

  // 「はい」だけ。選択肢が1つならそれ、複数ならどれか聞く
  if (YES_RE.test(s)) {
    if (offered.length === 1) return { ...none, key: offered[0] };
    return { ...none, ambiguous: true, kind: "which" };
  }

  return none;
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

/**
 * 承諾か断りか分からないときに聞き返す言葉。
 *
 * 「大丈夫です」のように、そのままでは決められない返事に対して、
 * 広げるのか広げないのかを二択で確かめる。
 */
export function confirmMessage(offered, labels) {
  if (offered.length === 1) {
    return `このまま探しますか？ それとも「${labels[offered[0]] ?? offered[0]}」でよろしいですか？`;
  }
  const list = offered.map((k, i) => `${i + 1}. ${labels[k] ?? k}`).join(" / ");
  return `広げずにこのまま探しますか？ 広げる場合は ${list} のどれかを教えてください。`;
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
