-- Project B · the SQL queries of the project.
-- Every block is used by queries/run_queries.py (report samples) and by the
-- Streamlit app (app/app.py). Parameters use psycopg2 named placeholders %(name)s,
-- so values are always sent bound, never pasted into the SQL text.
-- Author of every query: Odei Fernández Rodríguez (single-member group)

-- name: Q01
-- question: Which tags have the best-rated games on Steam, counting only tags used by at least N games?
-- uses: JOIN of 3 tables, GROUP BY + HAVING
SELECT t.name                              AS tag,
       count(*)                            AS games,
       round(avg(g.positive_ratio), 1)     AS avg_positive_ratio,
       sum(g.user_reviews)                 AS store_reviews
FROM tags t
JOIN game_tags gt USING (tag_id)
JOIN games g      USING (app_id)
GROUP BY t.name
HAVING count(*) >= %(min_games)s
ORDER BY avg_positive_ratio DESC, games DESC
LIMIT %(limit)s;

-- name: Q02
-- question: What were the most reviewed games of each release year, and how many of their reviewers recommend them?
-- uses: CTE, JOIN, window function RANK() OVER (PARTITION BY ...)
WITH per_game AS (
    SELECT g.app_id, g.title,
           extract(year FROM g.date_release)::int            AS release_year,
           count(*)                                          AS reviews,
           round(100.0 * avg(r.is_recommended::int), 1)      AS pct_recommended
    FROM games g
    JOIN recommendations r USING (app_id)
    WHERE g.date_release BETWEEN make_date(%(year_from)s, 1, 1) AND make_date(%(year_to)s, 12, 31)
    GROUP BY g.app_id, g.title, g.date_release
)
SELECT release_year, rnk, title, reviews, pct_recommended
FROM (SELECT p.*, RANK() OVER (PARTITION BY release_year ORDER BY reviews DESC) AS rnk
      FROM per_game p) ranked
WHERE rnk <= %(top)s
ORDER BY release_year DESC, rnk;

-- name: Q03
-- question: How did the number of reviews and the share of positive ones evolve month by month (optionally for one tag), and how much did each month grow over the same month one year before?
-- uses: CTE, subquery (IN), window functions LAG()
WITH monthly AS (
    SELECT date_trunc('month', r.review_date)::date          AS month,
           count(*)                                          AS reviews,
           round(100.0 * avg(r.is_recommended::int), 1)      AS pct_recommended
    FROM recommendations r
    WHERE r.review_date BETWEEN %(date_from)s AND %(date_to)s
      AND (%(tag)s IS NULL OR r.app_id IN (SELECT gt.app_id
                                           FROM game_tags gt JOIN tags t USING (tag_id)
                                           WHERE t.name = %(tag)s))
    GROUP BY 1
)
SELECT month, reviews, pct_recommended,
       reviews - LAG(reviews) OVER w                                   AS change_vs_prev_month,
       round(100.0 * (reviews - LAG(reviews, 12) OVER w)
                   / NULLIF(LAG(reviews, 12) OVER w, 0), 1)            AS growth_vs_year_before_pct
FROM monthly
WINDOW w AS (ORDER BY month)
ORDER BY month;

-- name: Q04
-- question: Do players recommend expensive games more than cheap or free ones, and do they play them longer before reviewing (optionally only games for one platform)?
-- uses: CTE (2 steps), CASE, JOIN, EXISTS subquery, ordered-set aggregate
WITH priced AS (
    SELECT g.app_id,
           CASE WHEN g.price_final = 0  THEN 1 WHEN g.price_final < 5  THEN 2
                WHEN g.price_final < 10 THEN 3 WHEN g.price_final < 20 THEN 4
                WHEN g.price_final < 40 THEN 5 ELSE 6 END            AS band
    FROM games g
    WHERE %(platform)s IS NULL
       OR EXISTS (SELECT 1 FROM game_platforms gp JOIN platforms p USING (platform_id)
                  WHERE gp.app_id = g.app_id AND p.name = %(platform)s)
), per_band AS (
    SELECT p.band,
           count(DISTINCT p.app_id)                                   AS games,
           count(*)                                                   AS reviews,
           round(100.0 * avg(r.is_recommended::int), 1)               AS pct_recommended,
           percentile_disc(0.5) WITHIN GROUP (ORDER BY r.hours)       AS median_hours
    FROM priced p
    JOIN recommendations r USING (app_id)
    GROUP BY p.band
)
SELECT (ARRAY['Free', '0.01-4.99', '5-9.99', '10-19.99', '20-39.99', '40+'])[band] AS price_band,
       games, reviews, pct_recommended, median_hours
FROM per_band
ORDER BY band;

-- name: Q05
-- question: Which games do the reviewers in this dataset like much more, or much less, than the Steam store score says?
-- uses: derived-table subquery with GROUP BY + HAVING, JOIN
SELECT g.title,
       g.positive_ratio                       AS steam_positive_ratio,
       s.pct_recommended                      AS dataset_pct_recommended,
       s.pct_recommended - g.positive_ratio   AS gap,
       s.reviews                              AS dataset_reviews
FROM games g
JOIN (SELECT app_id, count(*) AS reviews,
             round(100.0 * avg(is_recommended::int), 1) AS pct_recommended
      FROM recommendations
      GROUP BY app_id
      HAVING count(*) >= %(min_reviews)s) s USING (app_id)
ORDER BY abs(s.pct_recommended - g.positive_ratio) DESC
LIMIT %(limit)s;

-- name: Q06
-- question: Are reviews written during early access (before the release date) more or less positive than those written after release, by tag?
-- uses: JOIN of 4 tables, aggregates with FILTER, GROUP BY + HAVING
SELECT t.name                                                         AS tag,
       count(*) FILTER (WHERE r.review_date <  g.date_release)        AS early_access_reviews,
       round(100.0 * avg(r.is_recommended::int)
             FILTER (WHERE r.review_date <  g.date_release), 1)       AS pct_recommended_early,
       round(100.0 * avg(r.is_recommended::int)
             FILTER (WHERE r.review_date >= g.date_release), 1)       AS pct_recommended_after
FROM recommendations r
JOIN games g      USING (app_id)
JOIN game_tags gt ON gt.app_id = r.app_id AND gt.tag_rank <= 5
JOIN tags t       USING (tag_id)
GROUP BY t.name
HAVING count(*) FILTER (WHERE r.review_date < g.date_release) >= %(min_reviews)s
ORDER BY early_access_reviews DESC
LIMIT %(limit)s;

-- name: Q07
-- question: How has support for Mac, Linux and Steam Deck evolved among the games released each year?
-- uses: JOIN, GROUP BY, window function SUM() OVER (PARTITION BY ...)
WITH per_year AS (
    SELECT extract(year FROM g.date_release)::int AS release_year,
           p.name                                 AS platform,
           count(*)                               AS games
    FROM games g
    JOIN game_platforms gp USING (app_id)
    JOIN platforms p       USING (platform_id)
    WHERE g.date_release >= make_date(%(year_from)s, 1, 1)
    GROUP BY 1, 2
), totals AS (
    SELECT extract(year FROM date_release)::int AS release_year, count(*) AS games_released
    FROM games
    GROUP BY 1
)
SELECT y.release_year, y.platform, y.games, t.games_released,
       round(100.0 * y.games / t.games_released, 1)                          AS pct_of_year,
       sum(y.games) OVER (PARTITION BY y.platform ORDER BY y.release_year)   AS cumulative_games
FROM per_year y
JOIN totals t USING (release_year)
ORDER BY y.release_year, y.platform;

-- name: Q08
-- question: Which tags are over-represented among the best-rated games ('Overwhelmingly Positive') compared with the whole catalogue?
-- uses: 2 CTEs, scalar subqueries, JOIN, HAVING
WITH top_games AS (
    SELECT g.app_id
    FROM games g JOIN ratings ra USING (rating_id)
    WHERE ra.label = %(rating)s
), tag_counts AS (
    SELECT gt.tag_id,
           count(*)                                                    AS games_all,
           count(*) FILTER (WHERE gt.app_id IN (SELECT app_id FROM top_games)) AS games_top
    FROM game_tags gt
    GROUP BY gt.tag_id
)
SELECT t.name AS tag, tc.games_top, tc.games_all,
       round(100.0 * tc.games_top / (SELECT count(*) FROM top_games), 1)  AS pct_of_top_games,
       round(100.0 * tc.games_all / (SELECT count(*) FROM games), 1)      AS pct_of_all_games,
       round((1.0 * tc.games_top / (SELECT count(*) FROM top_games))
           / (1.0 * tc.games_all / (SELECT count(*) FROM games)), 2)      AS lift
FROM tag_counts tc
JOIN tags t USING (tag_id)
WHERE tc.games_top >= %(min_games)s
ORDER BY lift DESC
LIMIT %(limit)s;

-- name: Q09
-- question: Which reviewers write the reviews that other players find most helpful (among users with at least N reviews)?
-- uses: JOIN, GROUP BY + HAVING, window function RANK() over an aggregate
SELECT user_id, products, reviews, helpful_votes, helpful_per_review, pct_recommended, rnk
FROM (
    SELECT u.user_id, u.products,
           count(*)                                          AS reviews,
           sum(r.helpful)                                    AS helpful_votes,
           round(avg(r.helpful), 1)                          AS helpful_per_review,
           round(100.0 * avg(r.is_recommended::int), 1)      AS pct_recommended,
           RANK() OVER (ORDER BY avg(r.helpful) DESC)        AS rnk
    FROM users u
    JOIN recommendations r USING (user_id)
    GROUP BY u.user_id, u.products
    HAVING count(*) >= %(min_reviews)s
) ranked
WHERE rnk <= %(limit)s
ORDER BY rnk;

-- name: Q10
-- question: For the games whose title matches a search, how do their Steam score, price and reviews in the dataset compare?
-- uses: JOIN, two correlated subqueries, string_agg, ILIKE with a bound parameter
SELECT g.app_id, g.title, g.date_release, ra.label AS rating, g.positive_ratio,
       g.price_final, g.price_original, g.discount,
       (SELECT count(*) FROM recommendations r WHERE r.app_id = g.app_id) AS dataset_reviews,
       (SELECT string_agg(t.name, ', ' ORDER BY gt.tag_rank)
        FROM game_tags gt JOIN tags t USING (tag_id)
        WHERE gt.app_id = g.app_id AND gt.tag_rank <= 5)                  AS top_tags
FROM games g
JOIN ratings ra USING (rating_id)
WHERE g.title ILIKE '%%' || %(search)s || '%%'
ORDER BY g.user_reviews DESC
LIMIT %(limit)s;

-- name: Q11
-- question: If a sale (for example 50 percent) were applied to every paid game with a given tag, how many games would change and what would the average price become? (UPDATE inside a transaction, then ROLLBACK)
-- uses: data-modifying CTE (UPDATE ... RETURNING), IN subquery, run inside a transaction ended with ROLLBACK
WITH changed AS (
    UPDATE games g
    SET price_final = round(coalesce(g.price_original, g.price_final) * (1 - %(pct)s / 100.0), 2),
        discount    = CASE WHEN g.price_original IS NULL THEN NULL ELSE %(pct)s END
    WHERE g.price_final > 0
      AND g.app_id IN (SELECT gt.app_id FROM game_tags gt JOIN tags t USING (tag_id)
                       WHERE t.name = %(tag)s)
    RETURNING g.app_id, g.price_final
)
SELECT count(*)                       AS games_updated,
       round(avg(c.price_final), 2)   AS avg_price_after,
       (SELECT round(avg(g.price_final), 2) FROM games g
        WHERE g.app_id IN (SELECT app_id FROM changed)) AS avg_price_before
FROM changed c;

-- name: Q12
-- question: Do players who do not recommend a game stop playing it earlier? Median hours at review time, recommended vs not, for the most common tags.
-- uses: CTE, JOIN, GROUP BY + HAVING, ordered-set aggregates with FILTER
WITH tagged AS (
    SELECT t.name AS tag, r.is_recommended, r.hours
    FROM recommendations r
    JOIN game_tags gt ON gt.app_id = r.app_id AND gt.tag_rank = 1
    JOIN tags t       USING (tag_id)
)
SELECT tag,
       count(*)                                                               AS reviews,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hours) FILTER (WHERE is_recommended)     AS median_hours_recommended,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hours) FILTER (WHERE NOT is_recommended) AS median_hours_not_recommended
FROM tagged
GROUP BY tag
HAVING count(*) >= %(min_reviews)s
ORDER BY reviews DESC
LIMIT %(limit)s;
