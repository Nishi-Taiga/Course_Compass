# 疎通確認用 Worker（toritsu-compass-staging）

**アプリ本体ではありません。** 提供された Cloudflare アカウントで **D1 / KV / Workers AI の3つが実際に動く**ことを1回で証明するためだけの一式です。【P0】環境整備タスク用。

Pages ではなく **Workers** を使います（事務局マニュアルが新規は Workers 推奨と明記）。

## 中身

| ファイル | 中身 |
| --- | --- |
| `wrangler.jsonc` | assets(静的配信) + D1 + KV + AI のバインディング |
| `schema.sql` | schools / school_stats / stations / ward_stations / commute_times / school_clubs / sessions |
| `scripts/build_seed_sql.py` | `data/seed/*.csv` → `seed.sql` を生成 |
| `seed.sql` | 生成済み（Python が無くても投入できるようコミット済み・1.4MB） |
| `src/index.js` | `/health`, `/health/ai`, `/api/schools`, `/api/schools/:id` |
| `public/index.html` | ブラウザから疎通を叩くだけのページ |

投入されるデータ:

| テーブル | 行数 | 出所 |
| --- | --- | --- |
| `schools` | 187 | `data/seed/schools_master.csv` + designations + level_bands |
| `school_stats` | 1,314 | `data/seed/ratios_r4〜r8.csv` |
| `stations` | 647 | `prototype/index.html`（`scripts/extract_prototype_data.py` で抽出） |
| `ward_stations` | 49 | 同上（区市 → 代表駅） |
| `commute_times` | 31,703 | 同上（647駅 × 49区市・急行補正済） |
| `school_clubs` | 0 | Step2/6 で投入 |

⚠️ **通学時間データの所在**: `data/seed/` には元々無い。`build_commute_graph.py` は検証用でCSVを書かないため、
計算結果は `prototype/index.html` の `const D` に埋め込まれたものが唯一の完全版。
`scripts/extract_prototype_data.py` がそれをCSVに戻す。

⚠️ **島嶼部6区市**（大島町・三宅村・八丈町・小笠原村・新島村・神津島村）は鉄道が無いため
通学時間を持たない。該当**7校**は通学時間での絞り込みに乗らない（欠損ではなく仕様）。

---

## ⚠️ 先に済ませないとデプロイできないこと

1. 各自 Cloudflare 無料アカウント作成 → https://dash.cloudflare.com/sign-up
2. **チーム単位で利用申請**（メンバー全員のメールを1回で）→ https://forms.gle/hRVCyas3tfrGp1uF7
   - 申請メールは**ハッカソンSlackに登録済み**でないと受け付けられない
3. 招待メール承認 → ダッシュボード左上でハッカソン用チームに切替

---

## 手順

```bash
cd projects/toritsu-compass-staging/worker
npm install

npx wrangler login                        # ← ハッカソン用チームを選ぶ
npx wrangler d1 create course-compass-db
npx wrangler kv namespace create SESSIONS
#   → 出力された database_id / id を wrangler.jsonc の REPLACE_ME_AFTER_CREATE に貼る

npm run db:local && npm run dev           # http://localhost:8787/
npm run db:remote && npm run deploy       # 本番
```

`seed.sql` を作り直したいときだけ:

```bash
npm run seed:build      # python scripts/build_seed_sql.py
```

## 通ったと言える状態

公開URLの **`/health`** が次を返すこと:

```json
{ "ok": true, "schools": 187 }
```

`ok` は **D1接続・KV往復・件数一致（187校 / 1,314行 / 指定29校）が全部揃ったときだけ** true になります。件数がズレていると `ok: false` と `hint` が返ります。

Workers AI は **`/health/ai` を1回だけ**押して応答を確認（クレジット消費のため `/health` と分離してあります）。日本語の応答品質は **LLM選定ゲート（8/13）の入力**になるので、返ってきた文章をコピーして残してください。

ブラウザなら公開URLのトップページにボタンが3つ並んでいるので、そこから叩けます。

## つまずくところ

- ⚠️ **`--local` と `--remote` は中身が別物。** ローカルで187校出ていても本番DBは空です。`npm run db:remote` を忘れない（忘れると `/health` が `ok: false` + 件数0で返ります）
- ⚠️ **個人アカウントのままだと `wrangler login` は通るのにデプロイで権限エラー。** `npx wrangler logout` → もう一度 login してハッカソン用チームを選び直す
- ⚠️ **APIキーはソースに直書き禁止**（規約）。Secrets Store か `npx wrangler secret put <NAME>`
- モデルIDは `wrangler.jsonc` の `vars.AI_MODEL`（既定 `@cf/qwen/qwen3-30b-a3b-fp8`）。`/health/ai` がモデル不明のエラーを返したら、ダッシュボードの **Workers AI → Model Catalog** で実IDを確認して差し替える
- `commute_times` は最大14万行になる。投入時はバルクで（現状このテーブルは未投入）

## このタスクで併せて確認すること

仕様書 v0.1 は D1 / KV / R2 / Queues / AI Gateway / Cron Triggers を前提にしています。この Worker が確認するのは **D1 / KV / AI の3つだけ**なので、残りはダッシュボードで有効かを目視確認して報告してください。

- **Queues は通常 Paid プラン限定**。提供環境は Paid 相当との情報だが要確認（ここが一番の地雷）
- R2 / AI Gateway / Cron Triggers も併せて確認
