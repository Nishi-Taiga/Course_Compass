# Course Compass（仮称: 進路コンパス）

<!-- PRテスト -->

**都立高校探索ツール** — AIエージェントとの対話形式で、保護者が相談しながら志望校を探せるWebサービス。

都知事杯オープンデータ・ハッカソン2026 サービス開発部門 / **Team WINS**

- 仕様書: Notion「【P0】仕様確定」（機能仕様書・システム仕様書 v0.1）
- PJ管理: Notion「都知事杯ハッカソン2026」ページ（タスクDB・決定事項ログ）
- 提出締切: **8/23（ハッカソン本体 8/22-23）**

## リポジトリ構成

```
├── apps/
│   ├── web/                 # フロント（React + Vite）※未着手
│   └── api/                 # Workers（Hono）※未着手
├── packages/
│   ├── shared/              # 型定義・Zodスキーマ ※未着手
│   └── db/                  # D1 マイグレーション・シード ※未着手
├── scripts/                 # データ収集・整形（Pythonプロトタイプ）
├── data/
│   ├── fetched/             # 一次ソース原本（都教委PDF/CSV・再現性のためコミット）
│   └── seed/                # D1投入用の整形済みCSV（コミット対象）
├── docs/                    # データソース台帳ほか
└── .github/workflows/       # fetch-toritsu-data.yml（一次ソース自動取得）
```

## データ整備状況（2026-08-04時点）

| データ | 状態 | ファイル |
|---|---|---|
| 学校マスタ（187校・住所/学科/課程/指定区分） | ✅ | `data/seed/schools_master.csv` |
| 応募倍率 過去5年（R4〜R8・約260行/年） | ✅ | `data/seed/ratios_r*.csv` |
| 進学指導指定区分（29校・一次資料確定） | ✅ | `data/seed/designations.csv` |
| レベル帯ドラフト（band5/4/3=指定区分で確定、残り143校は西記入） | 🖊 記入待ち | `data/seed/level_bands_draft.csv` |
| 自己申告値→帯の境界表 | 🖊 記入待ち | `data/seed/level_anchors_draft.csv` |
| 通学時間（駅間概算グラフ・プロトタイプ動作済） | 🔧 | `scripts/build_commute_graph.py` |
| 部活・特色（各校サイト→LLM抽出） | 未着手（3校試行から） | — |

既知の注意点:

- **富士・大泉・白鴎・両国・武蔵の5校は高校からの募集を停止**した中高一貫校のため応募状況に存在しない（推薦対象からの除外要否を要検討）
- 倍率PDFは年度で列形式が異なる（R4-R5=男女別、R6以降=男女合同）。`parse_ratios.py` が吸収済み
- 通学時間の概算は急行・特快非対応（郊外で過大評価傾向）→ レンジ表示前提＋停車ロス係数の校正予定

## scripts の実行

```bash
pip install pypdfium2
python3 scripts/parse_ratios.py r4 r5 r6 r7 r8   # 倍率PDF → data/seed/ratios_*.csv
python3 scripts/build_school_master.py           # 学校マスタ整形
python3 scripts/build_level_bands.py             # レベル帯ドラフト生成
python3 scripts/build_commute_graph.py           # 通学時間グラフ検証（要 station_database DL）
```

一次ソースの再取得は GitHub Actions の `fetch-toritsu-data` を手動起動
（`scripts/fetch_urls.txt` のURLを2秒間隔で取得して `data/fetched/` にコミット）。

## データ出典・ライセンス

- 学校一覧・応募状況・指定区分: 東京都教育委員会 公開資料（東京都オープンデータ利用規約に基づく加工）
- 鉄道駅データ: [station_database](https://github.com/Seo-4d696b75/station_database)（CC BY-SA 4.0）
- 地図タイル（予定）: 国土地理院タイル（出典表記必須）

サービス内に出典クレジットを表示すること（免責表示の実装は機能仕様書§8.1参照）。
