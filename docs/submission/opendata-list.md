# 提出フォーム用: 利用オープンデータ登録リスト（最大10件）

登録形式: タイトル＋データURL のセット。上から優先順（フォームの枠が少ない場合は上から）。

| # | タイトル | URL |
|---|---|---|
| 1 | 東京都公立学校一覧（東京都教育委員会・公立学校統計調査報告書） | https://catalog.data.metro.tokyo.lg.jp/dataset/t000021d2000000176 |
| 2 | 都立高等学校 入学者選抜 応募状況（過去年度・令和4〜8年度） | https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/past/first_application |
| 3 | 令和8年度 都立高等学校 入学者選抜 応募状況（第一次募集・分割前期募集） | https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/application/submit |
| 4 | 進学指導重点校等の指定（東京都教育委員会） | https://www.kyoiku.metro.tokyo.lg.jp/school/designated_and_promotional_school/reformation/priority_school |
| 5 | 中学校卒業者の進路状況調査（東京都教育委員会） | https://www.kyoiku.metro.tokyo.lg.jp/about/statistics_and_research/career_report |
| 6 | station_database（全国鉄道駅・路線データ、CC BY-SA 4.0） | https://github.com/Seo-4d696b75/station_database |
| 7 | 東京都高等学校体育連盟 大会結果（過去記録） | https://www.tokyo-kotairen.gr.jp/past |
| 8 | 東京都高等学校野球連盟 試合結果 | https://www.tokyo-hbf.com |
| 9 | 東京都高等学校吹奏楽連盟 コンクール結果 | https://tokousuiren.com/c/competition/com_result/ |
| 10 | 高校生国際美術展 入賞・佳作一覧 | https://www.ihsaf.net |

⚠️ **OpenStreetMap が抜けている。** 4・5枚目の地図はOSMタイルで、画像内に
© OpenStreetMap contributors が写っている。資料は「すべての表示に出典を付けています」と
掲げているので、登録枠10件のどれかと入れ替えて登録するか判断が要る。
候補: 10番「高校生国際美術展」を外して OpenStreetMap（https://www.openstreetmap.org/copyright ・ODbL）を入れる。
資料側にはすでに6枚目へ脚注として記載済み。

登録枠に収まらなかった利用データ（参考・提出資料内で言及）:
- 日本高校ダンス部選手権 結果 https://dancestadium.com/high/
- 東京都高等学校文化連盟演劇部門（都大会） https://tkek.org/totaikai/
- 各校公式サイト（部活一覧・制服・アクセス・学校の言葉）

## URLの生存確認（2026-08-23）

10件すべてを実際に開いて確認した。#3 は都教委のURL改編で404になっていたため、
現行の常設ページ（募集・応募状況等 → 2 応募状況）に差し替えた。

⚠️ #1 東京都オープンデータカタログは AWS WAF のbot判定
（`x-amzn-waf-action: challenge`）が入るため、コマンドラインからは中身を確認できない。
カタログのトップ自体も同じ挙動なのでURL切れではないが、**提出前にブラウザで一度開くこと**。

## 画面キャプチャ（1600×900px・3点）

1. `capture1_kaiwa_teian.png` — 対話と提案（3つの圏・自宅の最寄駅からの地図）
2. `capture2_kuraberu_sheet.png` — くらべるシート（1枚地図・倍率5年推移）
3. `capture3_hyoshi.png` — 表紙画像

1・2 は画面を直すと古くなる。`node scripts/shoot_submission_captures.mjs` で
入力を固定したまま撮り直せる（3は表紙スライドなので対象外）。
