-- Secondary indexes, created AFTER the load (bulk loading is faster without them).
-- queries/index_benchmark.py measures the queries with and without them.
-- Author: Odei Fernández Rodríguez

-- name: create
-- FK recommendations.app_id is not indexed by its constraint. This index serves
-- "all reviews of a game", joins from games, and date ranges per game.
CREATE INDEX IF NOT EXISTS recommendations_app_date_idx
    ON recommendations (app_id, review_date) INCLUDE (is_recommended, hours);
-- Monthly trends over the whole dataset (Q03 without tag)
CREATE INDEX IF NOT EXISTS recommendations_date_idx ON recommendations (review_date);
-- Reverse side of the N:M tables: "games with tag X / on platform Y"
CREATE INDEX IF NOT EXISTS game_tags_tag_idx           ON game_tags (tag_id, app_id);
CREATE INDEX IF NOT EXISTS game_platforms_platform_idx ON game_platforms (platform_id, app_id);
CREATE INDEX IF NOT EXISTS games_rating_idx            ON games (rating_id);
CREATE INDEX IF NOT EXISTS games_release_idx           ON games (date_release);
-- recommendations.user_id is already the first column of UNIQUE (user_id, app_id).
ANALYZE;

-- name: drop
DROP INDEX IF EXISTS recommendations_app_date_idx, recommendations_date_idx,
    game_tags_tag_idx, game_platforms_platform_idx, games_rating_idx, games_release_idx;
