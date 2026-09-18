-- Recording script: F1, F2, F3 type these into the semsql prompt. Press Enter to run.
SELECT count(*) AS keyword_hits FROM reviews WHERE body ILIKE '%refund%';

WITH unhappy AS (SELECT * FROM reviews WHERE stars <= 2)
SELECT id, body,
       jev_noul(body, 'The customer is asking for their money back') AS p_refund,
       jev_grade(body, 'anger') AS anger
FROM unhappy
WHERE jev_noul(body, 'The customer is asking for their money back') > 0.8
ORDER BY anger DESC, p_refund DESC LIMIT 8;

WITH refunders AS (
  SELECT * FROM reviews
  WHERE stars <= 2
    AND jev_noul(body, 'The customer is asking for their money back') > 0.8)
SELECT jev_grade(body, 'anger') AS anger_grade,
       count(*) AS customers,
       count(*) FILTER (WHERE body NOT ILIKE '%refund%') AS never_say_refund,
       any_value(body) AS example
FROM refunders GROUP BY anger_grade ORDER BY anger_grade DESC;
