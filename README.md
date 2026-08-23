# 進路コンパス（Course Compass）

**都立高校探し、はじめの一歩。** 保護者がAIと相談しながら、お子さんに合う都立高校を見つける対話型Webサービスです。

都知事杯オープンデータ・ハッカソン2026 サービス開発部門 / **Team WINS**（西・寒河江・安田）

## 使ってみる

| | URL |
|---|---|
| **デモ（プロトタイプ）** | https://nishi-taiga.github.io/Course_Compass/prototype/ |
| 検索API（Cloudflare Workers） | https://toritsu-compass-staging.tokyo-odh-299.workers.dev |

最寄り駅 → 通学時間 → 内申点（5教科/実技） → 当日点 → 希望 → **いちばん大事にしたいこと**、の順に3分で聞き、安全圏・適正圏・挑戦圏に分けて候補を提案します。

## できること

- **対話で条件を聞き取り**: 「バスケがやりたい」「制服がない学校がいい」「定時制も見たい」を自由な言葉で
- **1020点満点の合否目安**: 換算内申（5教科＋実技×2）＋当日点で概算し、幅を持たせて判定（塾講師監修の参考値）
- **重視軸**: 「通学の近さ / 大学進学 / いま届きそうなところ」で並べ方を変える
- **部活で絞り込み**: 全189校・約5,000件の部活データ。実績（都大会〜全国）は公式記録から
- **くらべるシート**: 気になる学校を1枚に。自宅の最寄駅からの地図・実績・制服・倍率5年推移。**A4印刷対応**
- **高専・定時制もカバー**: ものづくり志望には高専を提案。点数で測れない学校は「測り方が違う」ことを明示

## 構成

```
prototype/index.html    デモ本体（単一HTML・GitHub Pages配信・API非依存）
projects/toritsu-compass-staging/worker/
  ├── src/              検索API（Cloudflare Workers + D1 + KV + Workers AI）
  ├── schema.sql        D1スキーマ（学校189・通学時間10.5万・部活5千・実績2.6千 ほか）
  └── scripts/smoke.mjs 本番APIの通しテスト（20項目）
scripts/                データ収集・整形（Python）＋ プロトタイプ回帰テスト（29項目）
data/fetched/           一次ソース原本（再現性のためコミット）
data/seed/              整形済みCSV（D1投入用）
```

会話の聞き取りは**規則ベースが主・LLM（Workers AI / Qwen3-30B）が補助**。数値や駅名は正規表現を優先し、LLMは初回相談など言い回しが多様な発話にだけ使います（応答0.7〜1.3秒/スロット）。

## データ出典

| データ | 出典 |
|---|---|
| 学校一覧・学科・所在地 | 東京都教育委員会 都立高校一覧（オープンデータ） |
| 応募倍率（R4〜R8） | 東京都教育委員会 入学者選抜応募状況 |
| 部活動一覧 | 各校公式サイト（189校） |
| 運動部の大会実績 | 東京都高等学校体育連盟 公式記録PDF |
| 硬式野球の実績 | 東京都高等学校野球連盟 試合結果 |
| 吹奏楽の実績 | 東京都高等学校吹奏楽連盟 コンクール結果PDF |
| 美術・書道の実績 | 高校生国際美術展 入賞・佳作PDF |
| 制服 | 各校公式サイト「制服・校章・校歌」ページ |
| 駅間所要時間 | station_database（CC BY-SA 4.0）から自前計算・急行補正済 |

詳細は [docs/data-sources.md](docs/data-sources.md)。

**個人情報の扱い**: 大会実績は**部の実績**として収集し、生徒の氏名・学年・記録は**収集の時点で読み取りません**（列自体を作らず、パーサに氏名混入の検査を入れて異常終了させる方式）。出典を示せないデータは載せません。

## 開発

```bash
# プロトタイプの回帰テスト（Playwright・29項目）
node scripts/check_prototype.mjs

# 本番APIの通しテスト（20項目）
cd projects/toritsu-compass-staging/worker && npm run smoke

# ランディングページに載せるくらべるシートの図を撮り直す
node scripts/shoot_landing_screenshots.mjs

# デプロイ（GitHub Actions・手動起動。データ更新時は seed=true）
gh workflow run deploy-worker.yml -f seed=false
```
