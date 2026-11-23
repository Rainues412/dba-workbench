SELECT id, title, priority, status, due_date, revision,
       CASE WHEN status != '已完成' AND date(due_date) < date('now', 'localtime')
          THEN 1 ELSE 0 END AS is_overdue
FROM tasks WHERE status != '已完成'
ORDER BY is_overdue DESC,
         CASE priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 ELSE 4 END,
         CASE status WHEN '进行中' THEN 0 WHEN '待处理' THEN 1 ELSE 2 END,
         date(due_date) ASC NULLS LAST, id DESC;
