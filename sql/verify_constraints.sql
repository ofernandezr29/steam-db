-- Run after the load to show that every constraint still exists and holds.
-- (Same information as pgAdmin > steam > Schemas > public > Tables > <table> > Constraints.)
-- Author: Odei Fernández Rodríguez

-- 1. Every constraint of the schema, with its type and definition
SELECT conrelid::regclass AS table_name,
       conname            AS constraint_name,
       CASE contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                    WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK' WHEN 'n' THEN 'NOT NULL' END AS type,
       convalidated       AS validated,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, contype, conname;

-- 2. Number of constraints per table and type
SELECT conrelid::regclass AS table_name,
       count(*) FILTER (WHERE contype = 'p') AS pk,
       count(*) FILTER (WHERE contype = 'f') AS fk,
       count(*) FILTER (WHERE contype = 'u') AS "unique",
       count(*) FILTER (WHERE contype = 'c') AS "check",
       count(*) FILTER (WHERE contype = 'n') AS not_null
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
GROUP BY 1 ORDER BY 1;

-- 3. Row counts after the load
SELECT 'ratings' AS table_name, count(*) AS rows FROM ratings
UNION ALL SELECT 'platforms', count(*) FROM platforms
UNION ALL SELECT 'games', count(*) FROM games
UNION ALL SELECT 'game_platforms', count(*) FROM game_platforms
UNION ALL SELECT 'tags', count(*) FROM tags
UNION ALL SELECT 'game_tags', count(*) FROM game_tags
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'recommendations', count(*) FROM recommendations;

-- 4. The constraints are enforced: each bad row is rejected (all inside a transaction
--    that is rolled back, so nothing changes)
BEGIN;
DO $$
DECLARE
    tests text[] := ARRAY[
      'INSERT INTO games (app_id, title, date_release, rating_id, positive_ratio, user_reviews, price_final) VALUES (13500, ''dup'', ''2020-01-01'', 5, 50, 10, 0)',
      'INSERT INTO games (app_id, title, date_release, rating_id, positive_ratio, user_reviews, price_final) VALUES (1, ''x'', ''2020-01-01'', 99, 50, 10, 0)',
      'INSERT INTO games (app_id, title, date_release, rating_id, positive_ratio, user_reviews, price_final) VALUES (1, ''x'', ''2020-01-01'', 5, 150, 10, 0)',
      'INSERT INTO games (app_id, title, date_release, rating_id, positive_ratio, user_reviews, price_final, price_original) VALUES (1, ''x'', ''2020-01-01'', 5, 50, 10, 20, 10)',
      'INSERT INTO recommendations SELECT review_id + 100000000, app_id, user_id, review_date, is_recommended, hours, helpful, funny FROM recommendations LIMIT 1',
      'INSERT INTO recommendations VALUES (999999999, 13500, 7360263, ''2020-01-01'', true, -1, 0, 0)',
      'INSERT INTO tags (tag_id, name) VALUES (9999, NULL)'];
    t text;
BEGIN
    FOREACH t IN ARRAY tests LOOP
        BEGIN
            EXECUTE t;
            RAISE NOTICE 'ACCEPTED (unexpected): %', t;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'rejected  [%] %', SQLSTATE, SQLERRM;
        END;
    END LOOP;
END $$;
ROLLBACK;
