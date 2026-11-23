SELECT
    (SELECT COUNT(*) FROM scripts) AS script_count,
    (SELECT COUNT(*) FROM articles) AS article_count,
    (SELECT COUNT(*) FROM tasks) AS task_total,
    (SELECT COUNT(*) FROM tasks WHERE status != '已完成') AS task_pending,
    (SELECT COUNT(*) FROM tasks WHERE status != '已完成' AND date(due_date) < date('now', 'localtime')) AS task_overdue,
    (SELECT COUNT(*) FROM customers) AS customer_count,
    (SELECT COUNT(*) FROM resources) AS resource_count,
    (SELECT COUNT(*) FROM vault_items) AS password_count;
