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
  ward              TEXT,                 -- 所在区市町村。commute_times.to_ward と対応
  postal_code       TEXT,
  address           TEXT,
  phone             TEXT,
  course_types      TEXT,                 -- 全日制 / 定時制 / 全日制・定時制
  departments       TEXT,                 -- 学科（普 / 商 など）
  students_fulltime INTEGER,
  designation       TEXT,                 -- 進学指導重点校 等（29校のみ）
  designation_rank  INTEGER,              -- 指定区分のランク（1が最上位）
  level_band_draft  INTEGER,              -- レベル帯ドラフト（西が8/10に確定予定・暫定値）
  source_master     TEXT,                 -- 出典（審査観点「出典の可視化」用）
  source_designation TEXT
);

CREATE INDEX idx_schools_ward        ON schools(ward);
CREATE INDEX idx_schools_designation ON schools(designation);
CREATE INDEX idx_schools_band        ON schools(level_band_draft);

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
-- 急行補正済み。build_commute_graph.py の計算結果をプロトタイプ経由で取り込んだもの。
-- 島嶼部6区市（大島町・三宅村・八丈町・小笠原村・新島村・神津島村）は鉄道が無いため対象外。
CREATE TABLE commute_times (
  from_station TEXT NOT NULL REFERENCES stations(station_name),
  to_ward      TEXT NOT NULL REFERENCES ward_stations(ward),
  minutes      INTEGER NOT NULL,
  PRIMARY KEY (from_station, to_ward)
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
