--# Recording script: F1..F4 type these into the semsql prompt. Press Enter to run.
--# Lines starting with "--" are typed on screen as captions. "--#" lines are not. No semicolons in captions.

-- The old way: find refund requests with keyword search
SELECT count(*) AS keyword_hits FROM reviews WHERE body ILIKE '%refund%';

-- Same question in plain English, inside SQL
-- Jev (TypeSafe) judges every review and returns a probability, graded by anger
WITH unhappy AS (SELECT * FROM reviews WHERE stars <= 2)
SELECT id, body,
       jev_noul(body, 'The customer is asking for their money back') AS p_refund,
       jev_grade(body, 'anger') AS anger
FROM unhappy
WHERE jev_noul(body, 'The customer is asking for their money back') > 0.8
ORDER BY anger DESC, p_refund DESC LIMIT 8;

-- Triage the whole refund queue by anger
-- Every judgment is cached, so this one costs $0.00
WITH refunders AS (
  SELECT * FROM reviews
  WHERE stars <= 2
    AND jev_noul(body, 'The customer is asking for their money back') > 0.8)
SELECT jev_grade(body, 'anger') AS anger_grade,
       count(*) AS customers,
       count(*) FILTER (WHERE body NOT ILIKE '%refund%') AS never_say_refund,
       any_value(body) AS example
FROM refunders GROUP BY anger_grade ORDER BY anger_grade DESC;

-- New question? Just change the English. No retraining, no prompt engineering
-- Which products are about to lose customers
SELECT product,
       count(*) AS about_to_leave,
       round(avg(jev_noul(body, 'The customer is threatening to stop buying from this shop or switch to a competitor')), 2) AS avg_p_churn,
       any_value(body) AS example
FROM reviews
WHERE stars <= 2
  AND jev_noul(body, 'The customer is threatening to stop buying from this shop or switch to a competitor') > 0.8
GROUP BY product ORDER BY about_to_leave DESC LIMIT 6;
