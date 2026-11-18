# Query results

## Q01. Which tags have the best-rated games on Steam, counting only tags used by at least N games?

*Uses:* JOIN of 3 tables, GROUP BY + HAVING  
*Parameters:* `{'min_games': 500, 'limit': 10}`  
*Time:* 0.05 s, 10 rows

```sql
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
```

| tag | games | avg_positive_ratio | store_reviews |
|---|---|---|---|
| Cats | 530 | 88.2 | 284,898 |
| Soundtrack | 872 | 87.9 | 347,060 |
| Precision Platformer | 762 | 87.8 | 221,804 |
| LGBTQ+ | 879 | 86.5 | 775,793 |
| Emotional | 1,292 | 86.1 | 1,188,926 |
| Minimalist | 2,322 | 85.7 | 784,124 |
| Abstract | 936 | 85.2 | 278,660 |
| Score Attack | 1,012 | 85.1 | 552,229 |
| Hand-drawn | 1,860 | 85.0 | 1,274,883 |
| Romance | 1,278 | 85.0 | 1,257,381 |



## Q02. What were the most reviewed games of each release year, and how many of their reviewers recommend them?

*Uses:* CTE, JOIN, window function RANK() OVER (PARTITION BY ...)  
*Parameters:* `{'year_from': 2018, 'year_to': 2022, 'top': 3}`  
*Time:* 1.24 s, 15 rows

```sql
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
```

| release_year | rnk | title | reviews | pct_recommended |
|---|---|---|---|---|
| 2,022 | 1 | Call of Duty® | 133,275 | 64.2 |
| 2,022 | 2 | Lost Ark | 129,522 | 72.6 |
| 2,022 | 3 | Mount & Blade II: Bannerlord | 127,532 | 87.5 |
| 2,021 | 1 | Forza Horizon 4 | 120,006 | 90.1 |
| 2,021 | 2 | Battlefield™ 2042 | 106,386 | 32.8 |
| 2,021 | 3 | New World | 96,548 | 69.7 |
| 2,020 | 1 | Cyberpunk 2077 | 226,414 | 74.5 |
| 2,020 | 2 | Sea of Thieves 2023 Edition | 149,875 | 89.5 |
| 2,020 | 3 | Factorio | 112,195 | 96.7 |
| 2,019 | 1 | Destiny 2 | 185,527 | 81.9 |
| 2,019 | 2 | Red Dead Redemption 2 | 158,370 | 88.9 |
| 2,019 | 3 | Space Engineers | 97,026 | 88.7 |
| 2,018 | 1 | Rust | 270,684 | 83.6 |
| 2,018 | 2 | Paladins® | 204,176 | 84.0 |
| 2,018 | 3 | Wallpaper Engine | 190,129 | 98.2 |



## Q03. How did the number of reviews and the share of positive ones evolve month by month (optionally for one tag), and how much did each month grow over the same month one year before?

*Uses:* CTE, subquery (IN), window functions LAG()  
*Parameters:* `{'date_from': datetime.date(2019, 1, 1), 'date_to': datetime.date(2022, 12, 31), 'tag': 'Roguelike'}`  
*Time:* 0.75 s, 48 rows

```sql
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
```

| month | reviews | pct_recommended | change_vs_prev_month | growth_vs_year_before_pct |
|---|---|---|---|---|
| 2019-01-01 | 5,464 | 82.2 | NULL | NULL |
| 2019-02-01 | 4,572 | 81.4 | -892 | NULL |
| 2019-03-01 | 4,293 | 82.1 | -279 | NULL |
| 2019-04-01 | 4,259 | 80.4 | -34 | NULL |
| 2019-05-01 | 5,306 | 78.4 | 1,047 | NULL |
| 2019-06-01 | 14,408 | 91.4 | 9,102 | NULL |
| 2019-07-01 | 12,655 | 88.6 | -1,753 | NULL |
| 2019-08-01 | 5,538 | 79.9 | -7,117 | NULL |
| 2019-09-01 | 5,023 | 80.8 | -515 | NULL |
| 2019-10-01 | 5,676 | 84.0 | 653 | NULL |
| 2019-11-01 | 19,288 | 93.0 | 13,612 | NULL |
| 2019-12-01 | 12,637 | 90.7 | -6,651 | NULL |
| 2020-01-01 | 10,418 | 88.8 | -2,219 | 90.7 |
| 2020-02-01 | 16,891 | 87.0 | 6,473 | 269.4 |
| 2020-03-01 | 13,482 | 87.9 | -3,409 | 214.0 |



## Q04. Do players recommend expensive games more than cheap or free ones, and do they play them longer before reviewing (optionally only games for one platform)?

*Uses:* CTE (2 steps), CASE, JOIN, EXISTS subquery, ordered-set aggregate  
*Parameters:* `{'platform': None}`  
*Time:* 25.45 s, 6 rows

```sql
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
```

| price_band | games | reviews | pct_recommended | median_hours |
|---|---|---|---|---|
| Free | 6,624 | 7,424,008 | 80.0 | 27.8 |
| 0.01-4.99 | 13,391 | 3,618,467 | 84.7 | 6.6 |
| 5-9.99 | 7,900 | 4,397,673 | 87.9 | 12.2 |
| 10-19.99 | 7,040 | 9,573,354 | 88.3 | 22.2 |
| 20-39.99 | 2,119 | 10,177,285 | 88.5 | 42.7 |
| 40+ | 536 | 5,963,986 | 83.3 | 60.3 |



## Q05. Which games do the reviewers in this dataset like much more, or much less, than the Steam store score says?

*Uses:* derived-table subquery with GROUP BY + HAVING, JOIN  
*Parameters:* `{'min_reviews': 5000, 'limit': 10}`  
*Time:* 1.13 s, 10 rows

```sql
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
```

| title | steam_positive_ratio | dataset_pct_recommended | gap | dataset_reviews |
|---|---|---|---|---|
| Grand Theft Auto V | 86 | 68.3 | -17.7 | 163,909 |
| Detention | 95 | 78.2 | -16.8 | 7,770 |
| NARAKA: BLADEPOINT | 75 | 59.2 | -15.8 | 30,308 |
| VRChat | 73 | 57.6 | -15.4 | 98,575 |
| Realm Royale Reforged | 75 | 61.1 | -13.9 | 11,905 |
| War Thunder | 75 | 61.4 | -13.6 | 80,609 |
| Book of Demons | 91 | 77.7 | -13.3 | 5,727 |
| Total War: THREE KINGDOMS | 82 | 68.8 | -13.2 | 49,373 |
| Heroes & Generals | 66 | 53.3 | -12.7 | 9,019 |
| IdleOn - The Idle MMO | 76 | 88.5 | 12.5 | 8,007 |



## Q06. Are reviews written during early access (before the release date) more or less positive than those written after release, by tag?

*Uses:* JOIN of 4 tables, aggregates with FILTER, GROUP BY + HAVING  
*Parameters:* `{'min_reviews': 50000, 'limit': 10}`  
*Time:* 4.19 s, 10 rows

```sql
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
```

| tag | early_access_reviews | pct_recommended_early | pct_recommended_after |
|---|---|---|---|
| Multiplayer | 478,233 | 77.7 | 82.0 |
| Action | 307,285 | 80.4 | 84.1 |
| Survival | 261,611 | 78.9 | 79.1 |
| Free to Play | 256,162 | 82.8 | 81.7 |
| Open World | 239,131 | 75.7 | 82.1 |
| Indie | 213,485 | 85.6 | 85.4 |
| Sandbox | 210,720 | 64.5 | 83.6 |
| Simulation | 203,896 | 86.1 | 81.7 |
| Singleplayer | 192,334 | 60.4 | 86.4 |
| FPS | 187,977 | 76.0 | 84.9 |



## Q07. How has support for Mac, Linux and Steam Deck evolved among the games released each year?

*Uses:* JOIN, GROUP BY, window function SUM() OVER (PARTITION BY ...)  
*Parameters:* `{'year_from': 2012}`  
*Time:* 0.04 s, 48 rows

```sql
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
```

| release_year | platform | games | games_released | pct_of_year | cumulative_games |
|---|---|---|---|---|---|
| 2,012 | Linux | 150 | 565 | 26.5 | 150 |
| 2,012 | Mac | 197 | 565 | 34.9 | 197 |
| 2,012 | Steam Deck | 565 | 565 | 100.0 | 565 |
| 2,012 | Windows | 555 | 565 | 98.2 | 555 |
| 2,013 | Linux | 314 | 822 | 38.2 | 464 |
| 2,013 | Mac | 360 | 822 | 43.8 | 557 |
| 2,013 | Steam Deck | 822 | 822 | 100.0 | 1387 |
| 2,013 | Windows | 816 | 822 | 99.3 | 1371 |
| 2,014 | Linux | 588 | 1,921 | 30.6 | 1052 |
| 2,014 | Mac | 800 | 1,921 | 41.6 | 1357 |
| 2,014 | Steam Deck | 1,921 | 1,921 | 100.0 | 3308 |
| 2,014 | Windows | 1,900 | 1,921 | 98.9 | 3271 |
| 2,015 | Linux | 869 | 2,963 | 29.3 | 1921 |
| 2,015 | Mac | 1,171 | 2,963 | 39.5 | 2528 |
| 2,015 | Steam Deck | 2,963 | 2,963 | 100.0 | 6271 |



## Q08. Which tags are over-represented among the best-rated games ('Overwhelmingly Positive') compared with the whole catalogue?

*Uses:* 2 CTEs, scalar subqueries, JOIN, HAVING  
*Parameters:* `{'rating': 'Overwhelmingly Positive', 'min_games': 20, 'limit': 10}`  
*Time:* 0.07 s, 10 rows

```sql
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
```

| tag | games_top | games_all | pct_of_top_games | pct_of_all_games | lift |
|---|---|---|---|---|---|
| Touch-Friendly | 25 | 214 | 2.3 | 0.4 | 5.35 |
| Addictive | 31 | 326 | 2.8 | 0.6 | 4.36 |
| Dating Sim | 94 | 1,091 | 8.5 | 2.1 | 3.95 |
| LGBTQ+ | 73 | 879 | 6.6 | 1.7 | 3.81 |
| Great Soundtrack | 317 | 3,912 | 28.6 | 7.7 | 3.71 |
| Romance | 98 | 1,278 | 8.8 | 2.5 | 3.51 |
| Cult Classic | 23 | 318 | 2.1 | 0.6 | 3.31 |
| Moddable | 49 | 713 | 4.4 | 1.4 | 3.15 |
| Blood | 23 | 338 | 2.1 | 0.7 | 3.12 |
| Classic | 88 | 1,316 | 7.9 | 2.6 | 3.06 |



## Q09. Which reviewers write the reviews that other players find most helpful (among users with at least N reviews)?

*Uses:* JOIN, GROUP BY + HAVING, window function RANK() over an aggregate  
*Parameters:* `{'min_reviews': 50, 'limit': 10}`  
*Time:* 22.42 s, 10 rows

```sql
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
```

| user_id | products | reviews | helpful_votes | helpful_per_review | pct_recommended | rnk |
|---|---|---|---|---|---|---|
| 5,860,500 | 556 | 129 | 70,096 | 543.4 | 82.9 | 1 |
| 14,274,968 | 2,313 | 81 | 43,063 | 531.6 | 100.0 | 2 |
| 12,012,557 | 929 | 58 | 23,139 | 398.9 | 100.0 | 3 |
| 12,686,573 | 2,670 | 59 | 18,219 | 308.8 | 78.0 | 4 |
| 8,983,002 | 8,163 | 52 | 12,239 | 235.4 | 94.2 | 5 |
| 13,085,543 | 1,164 | 82 | 19,280 | 235.1 | 95.1 | 6 |
| 5,016,837 | 5,836 | 119 | 27,150 | 228.2 | 0.8 | 7 |
| 7,390,717 | 1,269 | 52 | 11,650 | 224.0 | 75.0 | 8 |
| 13,644,747 | 342 | 51 | 11,043 | 216.5 | 90.2 | 9 |
| 8,203,128 | 258 | 64 | 13,816 | 215.9 | 73.4 | 10 |



## Q10. For the games whose title matches a search, how do their Steam score, price and reviews in the dataset compare?

*Uses:* JOIN, two correlated subqueries, string_agg, ILIKE with a bound parameter  
*Parameters:* `{'search': 'portal', 'limit': 10}`  
*Time:* 0.03 s, 10 rows

```sql
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
```

| app_id | title | date_release | rating | positive_ratio | price_final | price_original | discount | dataset_reviews | top_tags |
|---|---|---|---|---|---|---|---|---|---|
| 620 | Portal 2 | 2011-04-18 | Overwhelmingly Positive | 98 | 10.00 | NULL | NULL | 110,740 | NULL |
| 400 | Portal | 2007-10-10 | Overwhelmingly Positive | 98 | 10.00 | NULL | NULL | 52,705 | NULL |
| 317,400 | Portal Stories: Mel | 2015-06-25 | Overwhelmingly Positive | 96 | 0.00 | 0.00 | 0.0 | 10,209 | Free to Play, Puzzle, Adventure, Mod, Action |
| 1,255,980 | Portal Reloaded | 2021-04-19 | Overwhelmingly Positive | 96 | 0.00 | 0.00 | 0.0 | 8,777 | Free to Play, Action, Puzzle, Mod, First-Person |
| 374,040 | Portal Knights | 2017-05-18 | Very Positive | 83 | 6.99 | 19.99 | 65.0 | 9,708 | Adventure, Sandbox, Multiplayer, RPG, Building |
| 2,012,840 | Portal with RTX | 2022-12-08 | Mixed | 50 | 0.00 | 0.00 | 0.0 | 5,606 | Action, Puzzle, First-Person, Beautiful, Singleplayer |
| 684,410 | Bridge Constructor Portal | 2017-12-20 | Very Positive | 91 | 0.99 | 9.99 | 90.0 | 2,602 | Puzzle, Strategy, Simulation, Physics, Singleplayer |
| 446,750 | Portal Stories: VR | 2016-05-16 | Very Positive | 85 | 0.00 | 0.00 | 0.0 | 0 | Adventure, VR, Puzzle, Free to Play, Mod |
| 384,570 | Zanzarah: The Hidden Portal | 2015-08-20 | Mostly Positive | 70 | 7.99 | 7.99 | 0.0 | 409 | Adventure, Action, RPG, Fantasy, Female Protagonist |
| 104,600 | Portal 2 - The Final Hours | 2011-05-17 | Mostly Positive | 78 | 1.99 | 1.99 | 0.0 | 380 | Documentary, Story Rich, Action, Puzzle, Adventure |



## Q11. If a sale (for example 50 percent) were applied to every paid game with a given tag, how many games would change and what would the average price become? (UPDATE inside a transaction, then ROLLBACK)

*Uses:* data-modifying CTE (UPDATE ... RETURNING), IN subquery, run inside a transaction ended with ROLLBACK  
*Parameters:* `{'tag': 'Roguelike', 'pct': 50}`  
*Time:* 0.03 s, 1 rows

```sql
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
```

| games_updated | avg_price_after | avg_price_before |
|---|---|---|
| 1,800 | 5.67 | 10.52 |

After ROLLBACK the average price of those games is 10.52 (same as avg_price_before): the UPDATE left no trace.

## Q12. Do players who do not recommend a game stop playing it earlier? Median hours at review time, recommended vs not, for the most common tags.

*Uses:* CTE, JOIN, GROUP BY + HAVING, ordered-set aggregates with FILTER  
*Parameters:* `{'min_reviews': 100000, 'limit': 10}`  
*Time:* 11.29 s, 10 rows

```sql
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
```

| tag | reviews | median_hours_recommended | median_hours_not_recommended |
|---|---|---|---|
| Action | 1,799,581 | 11.9 | 3.2 |
| Free to Play | 1,733,307 | 11.0 | 2.5 |
| RPG | 965,002 | 32.6 | 9.3 |
| Adventure | 903,209 | 9.4 | 3.7 |
| Strategy | 855,735 | 29.6 | 7.0 |
| FPS | 796,024 | 14.8 | 5.0 |
| Open World | 694,832 | 32.0 | 13.7 |
| Simulation | 662,293 | 17.0 | 3.6 |
| Indie | 629,778 | 4.0 | 1.7 |
| Horror | 548,092 | 8.2 | 2.5 |


