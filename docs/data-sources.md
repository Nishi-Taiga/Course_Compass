# 都立高校探索ツール データソース台帳・取得手順

作成: 2026-08-04（Claude調査）。専用リポジトリ作成後は `docs/` へ移植する。

## 取得の分担

- **ローカルDL（西/メンバー）**: 都教委・都カタログ系はClaude実行環境からプロキシ不達のため、ブラウザでダウンロードして共有（リポジトリ作成後は `data/raw/` に配置）
- **Claude取得済み/取得可**: GitHub（raw.githubusercontent.com）経由のデータ

## 🔽 西さんへのダウンロード依頼リスト（優先順）

| 優先 | ファイル | URL | メモ |
|---|---|---|---|
| 1 | 東京都公立学校一覧CSV（令和7年度） | https://www.kyoiku.metro.tokyo.lg.jp/about/statistics_and_research/list_of_public_school/school_lists2025/report2025_csv | 学校マスタの土台。ページ内のCSVリンクから |
| 2 | 応募状況・過去5年分（第一次募集） | https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/past/first_application | 年度別リンク先のPDF/HTML表を一式（R4〜R8） |
| 3 | 同・最新（令和8年度最終応募状況） | https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/application/20260213_ichiji_final | |
| 4 | 進学指導指定校の一次資料 | https://www.kyoiku.metro.tokyo.lg.jp/school/designated_and_promotional_school/reformation/priority_school | 特別推進校・推進校の正確な全校名の確定用 |
| 5 | 指定校対比表PDF | https://www.kyoiku.metro.tokyo.lg.jp/documents/d/kyoiku/03_92 | 4の補強（現指定/次期指定の対比） |

分割後期・定時制の応募状況は優先度低（MVPは全日制第一次が主軸）:
- 分割後期: https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/past/second_application
- 定時制: https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/past/application_part-time

## 一次ソース台帳（全体）

### [1] 学校マスタ
- カタログ: https://catalog.data.metro.tokyo.lg.jp/dataset/t000021d2000000176 （公立学校統計調査報告書【東京都公立学校一覧】、組織=教育委員会）
- 都教委 年度別ページ: `.../list_of_public_school/school_lists{YYYY}`（2022〜2025の連番パターン）

### [2] 応募倍率（過去5年）
- ハブ: https://www.kyoiku.metro.tokyo.lg.jp/admission/high_school/past
- 年度別は `release20220214_01` 等の個別URL。**年度でPDF/HTML形式と表構造が変わる**前提でパーサを組む（取れた年度だけ表示の部分縮退方針）

### [3] 指定区分（レベル帯の根拠）
- **進学指導重点校（7校・確定）**: 日比谷、西、国立、八王子東、戸山、青山、立川（現行指定: 令和5年度〜令和10年3月）
- 特別推進校: 小山台、駒場、新宿、町田、国分寺、国際、小松川（候補・要一次資料確認）
- 推進校: 三田、豊多摩、竹早、北園、墨田川、城東、武蔵野北、小金井北、江北、江戸川、日野台、調布北、多摩科学技術、上野、昭和（候補・校数表記に13/15のブレあり要確認）

### [4] 学校基本統計・進路状況
- 都統計ポータル: https://www.toukei.metro.tokyo.lg.jp/gakkou/gk-index.htm
- 中学卒業者の進路状況（情報格差の根拠データ）: https://www.kyoiku.metro.tokyo.lg.jp/about/statistics_and_research/career_report （R7速報: 卒業者78,627人・進学率98.45%）

### [5] 鉄道・駅データ（通学時間計算）→ Claude取得可
- **メイン: `Seo-4d696b75/station_database`**（CC BY-SA 4.0・要クレジット表記）
  - 駅: `https://raw.githubusercontent.com/Seo-4d696b75/station_database/main/out/main/station.json`（全国9,372駅、東京都650駅）
  - 路線: `.../out/main/line.json`（636路線）
  - **路線別駅順: `.../out/main/line/{line_code}.json` の `station_list`**（隣接関係の源泉）
  - 特長: 物理的に同一の駅が単一IDに統合済み＝乗換の名寄せ不要
- 副次（クロスチェック用）: `piuccio/open-data-jp-railway-stations`（odpt統合、ライセンス表記なしに注意）
- 国土数値情報 N02（形状データ・必要時のみ）: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-v2_3.html
- ODPT（保険・要開発者登録〜2営業日）: https://developer.odpt.org/

### [6] 部活・特色（各校公式サイト）
- 収集はメンバーのパイプライン（Queues+LLM）。robots.txt確認・同一ホスト2秒以上間隔・UA明示
- 「だから都立高」学校別ページ: https://www.toritsuko.metro.tokyo.lg.jp/

## ライセンス・クレジット表記メモ

- station_database 利用時: CC BY-SA 4.0 のためサービス内クレジットに「駅データ: station_database (Seo-4d696b75) CC BY-SA 4.0」を記載
- 都オープンデータ: 原則CC BY 4.0相当（東京都オープンデータ利用規約）→「東京都教育委員会オープンデータを加工して作成」等の出典表記
- 地図タイル: 国土地理院（出典表記必須)
