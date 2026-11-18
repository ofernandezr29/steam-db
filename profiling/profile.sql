-- Data profile of the raw files, run on the text-only staging tables of schema raw
-- (filled by profiling/load_raw.py). Every number of the profile comes from here.
-- profiling/run_profile.py runs each block and writes profiling/profile_results.md
-- Author: Odei Fernández Rodríguez

-- name: 1. Row count of every file
SELECT 'games.csv' AS file, count(*) AS rows FROM raw.games
UNION ALL SELECT 'games_metadata.json', count(*) FROM raw.games_metadata
UNION ALL SELECT 'users.csv', count(*) FROM raw.users
UNION ALL SELECT 'recommendations.csv', count(*) FROM raw.recommendations;

-- name: 2. Candidate keys: are they really unique?
SELECT 'games.app_id' AS candidate_key, count(*) AS rows, count(DISTINCT app_id) AS distinct_values FROM raw.games
UNION ALL SELECT 'games.title', count(*), count(DISTINCT title) FROM raw.games
UNION ALL SELECT 'games_metadata.app_id', count(*), count(DISTINCT doc->>'app_id') FROM raw.games_metadata
UNION ALL SELECT 'users.user_id', count(*), count(DISTINCT user_id) FROM raw.users
UNION ALL SELECT 'recommendations.review_id', count(*), count(DISTINCT review_id) FROM raw.recommendations
UNION ALL SELECT 'recommendations.(user_id, app_id)', count(*),
       (SELECT count(*) FROM (SELECT DISTINCT user_id, app_id FROM raw.recommendations) d)
FROM raw.recommendations;

-- name: 3. Nulls / empty values per column (games)
SELECT count(*) FILTER (WHERE coalesce(app_id, '') = '')         AS app_id,
       count(*) FILTER (WHERE coalesce(btrim(title), '') = '')    AS title,
       count(*) FILTER (WHERE coalesce(date_release, '') = '')    AS date_release,
       count(*) FILTER (WHERE coalesce(rating, '') = '')          AS rating,
       count(*) FILTER (WHERE coalesce(positive_ratio, '') = '')  AS positive_ratio,
       count(*) FILTER (WHERE coalesce(user_reviews, '') = '')    AS user_reviews,
       count(*) FILTER (WHERE coalesce(price_final, '') = '')     AS price_final,
       count(*) FILTER (WHERE coalesce(price_original, '') = '')  AS price_original,
       count(*) FILTER (WHERE coalesce(discount, '') = '')        AS discount,
       count(*) FILTER (WHERE coalesce(win, '') = '' OR coalesce(mac, '') = ''
                         OR coalesce(linux, '') = '' OR coalesce(steam_deck, '') = '') AS platform_flags
FROM raw.games;

-- name: 4. Nulls / empty values per column (games_metadata.json)
SELECT count(*) FILTER (WHERE doc->>'app_id' IS NULL)                      AS app_id,
       count(*) FILTER (WHERE coalesce(btrim(doc->>'description'), '') = '') AS description_empty,
       count(*) FILTER (WHERE jsonb_array_length(doc->'tags') = 0)          AS tags_empty_list
FROM raw.games_metadata;

-- name: 5. Nulls / empty values per column (users, recommendations)
SELECT 'users' AS file,
       count(*) FILTER (WHERE coalesce(user_id, '') = '' OR coalesce(products, '') = ''
                         OR coalesce(reviews, '') = '') AS rows_with_an_empty_value
FROM raw.users
UNION ALL
SELECT 'recommendations',
       count(*) FILTER (WHERE coalesce(app_id, '') = '' OR coalesce(helpful, '') = ''
                         OR coalesce(funny, '') = '' OR coalesce(date, '') = ''
                         OR coalesce(is_recommended, '') = '' OR coalesce(hours, '') = ''
                         OR coalesce(user_id, '') = '' OR coalesce(review_id, '') = '')
FROM raw.recommendations;

-- name: 6. Formats: values that do not match the expected pattern
SELECT 'games.date_release YYYY-MM-DD' AS check, count(*) FILTER (WHERE date_release !~ '^\d{4}-\d{2}-\d{2}$') AS bad FROM raw.games
UNION ALL SELECT 'games.app_id integer', count(*) FILTER (WHERE app_id !~ '^\d+$') FROM raw.games
UNION ALL SELECT 'games.prices 0.00 decimal', count(*) FILTER (WHERE price_final !~ '^\d+\.\d+$' OR price_original !~ '^\d+\.\d+$') FROM raw.games
UNION ALL SELECT 'games.platform flags true/false', count(*) FILTER (WHERE NOT (win IN ('true','false') AND mac IN ('true','false') AND linux IN ('true','false') AND steam_deck IN ('true','false'))) FROM raw.games
UNION ALL SELECT 'users.* integers', count(*) FILTER (WHERE user_id !~ '^\d+$' OR products !~ '^\d+$' OR reviews !~ '^\d+$') FROM raw.users
UNION ALL SELECT 'recommendations.date YYYY-MM-DD', count(*) FILTER (WHERE date !~ '^\d{4}-\d{2}-\d{2}$') FROM raw.recommendations
UNION ALL SELECT 'recommendations.hours one decimal', count(*) FILTER (WHERE hours !~ '^\d+\.\d$') FROM raw.recommendations
UNION ALL SELECT 'recommendations.is_recommended true/false', count(*) FILTER (WHERE is_recommended NOT IN ('true','false')) FROM raw.recommendations;

-- name: 7. Value ranges of dates and numbers
SELECT 'games.date_release' AS col, min(date_release::date)::text AS min, max(date_release::date)::text AS max FROM raw.games
UNION ALL SELECT 'games.positive_ratio', min(positive_ratio::int)::text, max(positive_ratio::int)::text FROM raw.games
UNION ALL SELECT 'games.user_reviews', min(user_reviews::int)::text, max(user_reviews::int)::text FROM raw.games
UNION ALL SELECT 'games.price_final', min(price_final::numeric)::text, max(price_final::numeric)::text FROM raw.games
UNION ALL SELECT 'games.price_original', min(price_original::numeric)::text, max(price_original::numeric)::text FROM raw.games
UNION ALL SELECT 'games.discount', min(discount::numeric)::text, max(discount::numeric)::text FROM raw.games
UNION ALL SELECT 'tags per game', min(jsonb_array_length(doc->'tags'))::text, max(jsonb_array_length(doc->'tags'))::text FROM raw.games_metadata
UNION ALL SELECT 'users.products', min(products::int)::text, max(products::int)::text FROM raw.users
UNION ALL SELECT 'users.reviews', min(reviews::int)::text, max(reviews::int)::text FROM raw.users
UNION ALL SELECT 'recommendations.date', min(date::date)::text, max(date::date)::text FROM raw.recommendations
UNION ALL SELECT 'recommendations.hours', min(hours::numeric)::text, max(hours::numeric)::text FROM raw.recommendations
UNION ALL SELECT 'recommendations.helpful', min(helpful::int)::text, max(helpful::int)::text FROM raw.recommendations
UNION ALL SELECT 'recommendations.funny', min(funny::int)::text, max(funny::int)::text FROM raw.recommendations;

-- name: 8. Coded values: rating labels and the positive_ratio / user_reviews range of each
SELECT rating, count(*) AS games,
       min(positive_ratio::int) AS min_ratio, max(positive_ratio::int) AS max_ratio,
       min(user_reviews::int) AS min_reviews, max(user_reviews::int) AS max_reviews
FROM raw.games GROUP BY rating ORDER BY min(positive_ratio::int), min(user_reviews::int);

-- name: 9. Coded values: platform flag combinations
SELECT win, mac, linux, steam_deck, count(*) AS games
FROM raw.games GROUP BY 1, 2, 3, 4 ORDER BY games DESC;

-- name: 10. Coded values: distinct tags
SELECT count(DISTINCT t) AS distinct_tags,
       count(DISTINCT lower(btrim(t))) AS distinct_after_lower_trim,
       max(length(t)) AS longest_tag
FROM raw.games_metadata, jsonb_array_elements_text(doc->'tags') AS t;

-- name: 11. Referential integrity between files (orphans)
SELECT 'recommendations.app_id not in games' AS check, count(*) AS rows
FROM raw.recommendations r LEFT JOIN raw.games g ON g.app_id = r.app_id WHERE g.app_id IS NULL
UNION ALL SELECT 'recommendations.user_id not in users', count(*)
FROM raw.recommendations r LEFT JOIN raw.users u ON u.user_id = r.user_id WHERE u.user_id IS NULL
UNION ALL SELECT 'games_metadata.app_id not in games', count(*)
FROM raw.games_metadata m LEFT JOIN raw.games g ON g.app_id = m.doc->>'app_id' WHERE g.app_id IS NULL
UNION ALL SELECT 'games without metadata', count(*)
FROM raw.games g LEFT JOIN raw.games_metadata m ON m.doc->>'app_id' = g.app_id WHERE m.line_no IS NULL
UNION ALL SELECT 'games without any recommendation', count(*)
FROM raw.games g LEFT JOIN (SELECT DISTINCT app_id FROM raw.recommendations) r ON r.app_id = g.app_id
WHERE r.app_id IS NULL;

-- name: 12. Unexpected: paid games whose original price is 0.00
SELECT count(*) FILTER (WHERE price_original::numeric = 0 AND price_final::numeric > 0) AS final_gt_0_original_0,
       count(*) FILTER (WHERE price_final::numeric > price_original::numeric) AS final_gt_original,
       count(*) FILTER (WHERE price_original::numeric = 0 AND price_final::numeric = 0) AS free_games
FROM raw.games;

-- name: 13. Unexpected: the same user reviews the same game twice
SELECT r.user_id, r.app_id, r.review_id, r.date, r.is_recommended, r.hours, r.helpful
FROM raw.recommendations r
JOIN (SELECT user_id, app_id FROM raw.recommendations
      GROUP BY user_id, app_id HAVING count(*) > 1) d USING (user_id, app_id)
ORDER BY r.user_id, r.app_id, r.date
LIMIT 10;

-- name: 14. Is users.reviews derived from recommendations?
WITH c AS (SELECT user_id, count(*) AS n FROM raw.recommendations GROUP BY user_id)
SELECT count(*) AS users,
       count(*) FILTER (WHERE coalesce(c.n, 0) = u.reviews::int) AS reviews_equals_count,
       count(*) FILTER (WHERE coalesce(c.n, 0) <> u.reviews::int) AS different
FROM raw.users u LEFT JOIN c USING (user_id);

-- name: 15. Unexpected: reviews written before the game's release date (early access)
SELECT count(*) AS reviews_before_release,
       count(DISTINCT r.app_id) AS games_affected,
       round(100.0 * count(*) / (SELECT count(*) FROM raw.recommendations), 1) AS pct_of_reviews
FROM raw.recommendations r JOIN raw.games g USING (app_id)
WHERE r.date::date < g.date_release::date;

-- name: 16. Unexpected: hours at the extremes, users with 0 products
SELECT (SELECT count(*) FROM raw.recommendations WHERE hours::numeric = 0)    AS reviews_with_0_hours,
       (SELECT count(*) FROM raw.recommendations WHERE hours::numeric = 1000) AS reviews_with_1000_hours,
       (SELECT count(*) FROM raw.users WHERE products::int = 0)                AS users_0_products,
       (SELECT count(*) FROM raw.users WHERE products::int = 0 AND reviews::int > 0) AS users_0_products_with_reviews,
       (SELECT count(*) FROM raw.users WHERE reviews::int = 0)                 AS users_without_reviews;
