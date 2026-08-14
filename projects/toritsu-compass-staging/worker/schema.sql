-- D1 スキーマ（仕様書§6.4 のうち MVP必須テーブル）
-- 何度流しても同じ結果になるよう、DROP → CREATE で作り直す。

DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS school_clubs;
DROP TABLE IF EXISTS commute_times;
DROP TABLE IF EXISTS ward_stations;
DROP TABLE IF EXISTS stations;
DROP TABLE IF EXISTS school_stats;
DROP TABLE IF EXISTS schools;

-- 学校マスタ（187校）。年度で変わらない属性だけを持つ。
CREATE TABLE schools (
  school_number     TEXT PRIMARY KEY,     -- 都教委の学校番号（先頭0が消えないよう TEXT）
  name              TEXT NOT NULL,
  name_kana         TEXT,
  ward              TEXT,                 -- 所在区市町村
  postal_code       TEXT,
  address           TEXT,
  phone             TEXT,
  course_types      TEXT,                 -- 全日制 / 定時制 / 全日制・定時制
  departments       TEXT,                 -- 学科（普 / 商 など）
  students_fulltime INTEGER,
  designation       TEXT,                 -- 進学指導重点校 等（29校のみ）
  designation_rank  INTEGER,              -- 指定区分のランク（1が最上位）

  -- 判定モデル（1020点の差分方式）。レベル帯1〜5は廃止した。
  -- 帯だと境界（内申39と40）で丸ごと1段ずれるうえ、帯ごとの校数を人手で
  -- 均す必要があった。差分方式なら閾値1箇所の調整で済む。
  target_score      INTEGER,              -- 合格の目安点（1020点満点）。NULLなら数値判定しない
  selection_type    TEXT,                 -- std / jiko / keisha / fukasawa / ratio64 / no_exam
  selection_note    TEXT,                 -- 区分の注意書き。表示するだけで計算式は分岐しない
  score_layer       TEXT,                 -- 目安点の層ラベル（重点校 等）
  no_hs_admission   INTEGER DEFAULT 0,    -- 1なら高校からの募集停止（中高一貫5校）

  source_master     TEXT,                 -- 出典（審査観点「出典の可視化」用）
  source_designation TEXT,
  source_target_score TEXT
);

CREATE INDEX idx_schools_ward        ON schools(ward);
CREATE INDEX idx_schools_designation ON schools(designation);
CREATE INDEX idx_schools_target      ON schools(target_score);

-- 応募倍率（R4〜R8 / 1,314行）。毎年更新されるのでマスタと分ける。
CREATE TABLE school_stats (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  school_number  TEXT NOT NULL REFERENCES schools(school_number),
  year           TEXT NOT NULL,           -- 'r4' 〜 'r8'
  department     TEXT,
  sub_department TEXT,
  capacity       INTEGER,
  applicants     INTEGER,
  ratio          REAL,
  source         TEXT                     -- 出典
);

CREATE INDEX idx_stats_school ON school_stats(school_number);
CREATE INDEX idx_stats_year   ON school_stats(year);

-- 駅マスタ（647駅）
CREATE TABLE stations (
  station_name TEXT PRIMARY KEY,
  lat          REAL,
  lon          REAL
);

-- 区市の代表駅（49区市）。学校は最寄駅を持たないため、区市の代表駅で代表させる。
CREATE TABLE ward_stations (
  ward        TEXT PRIMARY KEY,
  rep_station TEXT NOT NULL REFERENCES stations(station_name)
);

-- 駅→区市の所要時間（647 × 49 = 31,703行）
-- 通学時間。出発駅ごと・**学校ごと**に持つ（2026-08-14に区単位から作り直した）。
--   通学時間 = 鉄道(出発駅 → アクセス起点駅) + アクセス(徒歩 または バス)
-- アクセス起点駅は各校サイトのアクセスページが挙げた駅。複数あれば最短を採る。
-- 以前は 駅×区(49) だったため、同じ区の学校は所要時間が全部同じ値だった。
-- 例: 新宿→練馬区の9校はいずれも20分だったが、いま 23分(練馬工科)〜58分(大泉桜) と分かれる。
-- 島嶼部7校は鉄道が無いため行が入らない。scripts/build_school_commute.py で再生成できる。
CREATE TABLE commute_times (
  from_station  TEXT NOT NULL REFERENCES stations(station_name),
  school_number TEXT NOT NULL REFERENCES schools(school_number),
  minutes       INTEGER NOT NULL,
  via_station   TEXT,                  -- 実際に降りる駅。画面で「◯◯駅から」と出せる
  access_mode   TEXT,                  -- walk / bus。バスなら school_access に系統が入っている
  PRIMARY KEY (from_station, school_number)
);

-- 「出発駅から N分以内」を引くための索引。受け入れ条件の1秒以内はこれで満たす。
CREATE INDEX idx_commute_from_min ON commute_times(from_station, minutes);

-- 部活・特色（Step2/6で投入）。抽出時は正規化せず生の文字列で保存し、
-- 正規化は後段でかける（西が辞書を監修するため、先に潰すと直せなくなる）。
CREATE TABLE school_clubs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  school_number TEXT NOT NULL REFERENCES schools(school_number),
  raw_name      TEXT NOT NULL,            -- 学校サイト上の表記そのまま
  normalized    TEXT,                     -- 正規化後（後段で埋める）
  category      TEXT,                     -- 運動部 / 文化部 など
  source_url    TEXT,
  fetched_at    TEXT
);

CREATE INDEX idx_clubs_school ON school_clubs(school_number);
CREATE INDEX idx_clubs_norm   ON school_clubs(normalized);

-- 対話セッション。本体はKV（TTL 24h）に置くが、
-- LLM呼び出し回数の上限管理（仕様書§3.6）を落とさないための控えを持つ。
CREATE TABLE sessions (
  session_id  TEXT PRIMARY KEY,
  created_at  TEXT NOT NULL,
  updated_at  TEXT,
  state       TEXT,                       -- S1〜S9
  llm_calls   INTEGER NOT NULL DEFAULT 0
);
