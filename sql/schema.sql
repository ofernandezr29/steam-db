-- Project B · Steam game recommendations
SET client_min_messages = warning;
-- Physical schema. Run this BEFORE the load: etl/load.py only inserts rows.
--
--   psql -h localhost -U postgres -d steam -f sql/schema.sql
--
-- Author: Odei Fernández Rodríguez

DROP TABLE IF EXISTS recommendations, game_tags, game_platforms, tags,
                     platforms, users, games, ratings CASCADE;

-- Steam's review score labels. rank_order sorts them from worst (1) to best (9).
CREATE TABLE ratings (
    rating_id   smallint     PRIMARY KEY,
    label       varchar(30)  NOT NULL UNIQUE,
    rank_order  smallint     NOT NULL UNIQUE CHECK (rank_order BETWEEN 1 AND 9)
);

CREATE TABLE games (
    app_id          integer       PRIMARY KEY CHECK (app_id > 0),
    title           varchar(200)  NOT NULL CHECK (btrim(title) <> ''),
    date_release    date          NOT NULL CHECK (date_release >= DATE '1990-01-01'),
    rating_id       smallint      NOT NULL REFERENCES ratings (rating_id),
    positive_ratio  smallint      NOT NULL CHECK (positive_ratio BETWEEN 0 AND 100),
    user_reviews    integer       NOT NULL CHECK (user_reviews >= 0),
    price_final     numeric(6,2)  NOT NULL CHECK (price_final >= 0),
    price_original  numeric(6,2)  CHECK (price_original >= 0),          -- NULL = unknown
    discount        numeric(4,1)  CHECK (discount BETWEEN 0 AND 100),  -- NULL = unknown
    description     text,                                               -- NULL = none given
    CONSTRAINT games_final_le_original
        CHECK (price_original IS NULL OR price_final <= price_original)
);

CREATE TABLE platforms (
    platform_id  smallint     PRIMARY KEY,
    name         varchar(20)  NOT NULL UNIQUE
);

-- N:M games <-> platforms (replaces the four boolean columns of games.csv)
CREATE TABLE game_platforms (
    app_id       integer   NOT NULL REFERENCES games (app_id) ON DELETE CASCADE,
    platform_id  smallint  NOT NULL REFERENCES platforms (platform_id),
    PRIMARY KEY (app_id, platform_id)
);

CREATE TABLE tags (
    tag_id  smallint     PRIMARY KEY,
    name    varchar(40)  NOT NULL UNIQUE
);

-- N:M games <-> tags. tag_rank keeps the order Steam shows (1 = most voted tag).
CREATE TABLE game_tags (
    app_id    integer   NOT NULL REFERENCES games (app_id) ON DELETE CASCADE,
    tag_id    smallint  NOT NULL REFERENCES tags (tag_id),
    tag_rank  smallint  NOT NULL CHECK (tag_rank BETWEEN 1 AND 20),
    PRIMARY KEY (app_id, tag_id),
    UNIQUE (app_id, tag_rank)
);

CREATE TABLE users (
    user_id   integer  PRIMARY KEY CHECK (user_id >= 0),
    products  integer  NOT NULL CHECK (products >= 0)
);

-- One review of one game by one user (N:M users <-> games with attributes)
CREATE TABLE recommendations (
    review_id       integer       PRIMARY KEY CHECK (review_id >= 0),
    app_id          integer       NOT NULL REFERENCES games (app_id),
    user_id         integer       NOT NULL REFERENCES users (user_id),
    review_date     date          NOT NULL CHECK (review_date >= DATE '2003-09-12'), -- Steam launch
    is_recommended  boolean       NOT NULL,
    hours           numeric(5,1)  NOT NULL CHECK (hours >= 0),
    helpful         integer       NOT NULL CHECK (helpful >= 0),
    funny           integer       NOT NULL CHECK (funny >= 0),
    CONSTRAINT recommendations_one_per_user_game UNIQUE (user_id, app_id)
);

COMMENT ON COLUMN games.price_original IS 'NULL when the source had 0.00 but price_final > 0 (unknown original price)';
COMMENT ON COLUMN games.user_reviews   IS 'Total reviews on the Steam store (not only the ones in recommendations)';
COMMENT ON COLUMN recommendations.hours IS 'Hours played when the review was written; the source caps it at 1000';
