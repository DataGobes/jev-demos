-- 1. Plain SQL still works.
SELECT * FROM products LIMIT 20;

-- 2. Same data, one new clause. Jev picks the chart.
SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending';

-- 3. Same query, different question -> different chart. No SQL changed.
SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'which region sold the most overall';

-- 4. Run #2 again: cache hit, jev 0ms.

-- 5. Jev knows customer_id is not a measure. Type rules cannot.
SELECT segment, customer_id, sum(revenue) AS revenue
FROM orders JOIN customers USING (customer_id) GROUP BY ALL LIMIT 2000
VISUALIZE 'which customer segment spends the most';

-- 6. Three intents -> a dashboard, still one Jev request.
SELECT date_trunc('month', order_date) AS order_month, region, channel, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending', 'which channel is biggest', 'where do region and channel combine best';
