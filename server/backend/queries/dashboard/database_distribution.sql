WITH database_types(name, sort_order) AS (
    VALUES
        ('Oracle', 1),
        ('MySQL', 2),
        ('PostgreSQL', 3),
        ('SQL Server', 4),
        ('Linux', 5),
        ('Redis', 6),
        ('MongoDB', 7),
        ('其他', 8)
),
database_counts AS (
    SELECT
        CASE
            WHEN db_type IN ('Oracle', 'MySQL', 'PostgreSQL', 'SQL Server', 'Linux', 'Redis', 'MongoDB')
            THEN db_type ELSE '其他'
        END AS name,
        COUNT(*) AS item_count
    FROM scripts
    GROUP BY name
    UNION ALL
    SELECT
        CASE
            WHEN wb_db IN ('Oracle', 'MySQL', 'PostgreSQL', 'SQL Server', 'Linux', 'Redis', 'MongoDB')
            THEN wb_db ELSE '其他'
        END AS name,
        COUNT(*) AS item_count
    FROM articles
    GROUP BY name
)
SELECT database_types.name, COALESCE(SUM(database_counts.item_count), 0) AS count
FROM database_types
LEFT JOIN database_counts ON database_counts.name = database_types.name
GROUP BY database_types.name, database_types.sort_order
ORDER BY database_types.sort_order;
