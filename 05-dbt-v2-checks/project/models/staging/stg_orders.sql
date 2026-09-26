select * from (values
    (101, 1, date '2024-04-01', 'shipped',   42.50),
    (102, 1, date '2024-04-03', 'shipped',   17.00),
    (103, 2, date '2024-04-03', 'returned',  99.99),
    (104, 3, date '2024-04-05', 'placed',     8.25)
) as t(order_id, customer_id, order_date, status, order_total)
