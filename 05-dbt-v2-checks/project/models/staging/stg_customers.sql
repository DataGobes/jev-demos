select * from (values
    (1, 'Ada',    'Lovelace', 'ada@example.com',    date '2024-01-03'),
    (2, 'Grace',  'Hopper',   'grace@example.com',  date '2024-02-11'),
    (3, 'Edsger', 'Dijkstra', 'edsger@example.com', date '2024-03-20')
) as t(customer_id, first_name, last_name, email, signup_date)
