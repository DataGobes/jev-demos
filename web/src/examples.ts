export const EXAMPLES: { label: string; sql: string }[] = [
  { label: "Regions trending", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'how are regions trending'" },
  { label: "Same query, different question", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'which region sold the most overall'" },
  { label: "Channel share", sql: "SELECT channel, sum(revenue) AS revenue FROM orders GROUP BY ALL\nVISUALIZE 'what share of revenue comes from each channel'" },
  { label: "Price vs rating", sql: "SELECT price, rating, category FROM products\nVISUALIZE 'do more expensive products get better ratings'" },
  { label: "Identifier trap", sql: "SELECT segment, customer_id, sum(revenue) AS revenue\nFROM orders JOIN customers USING (customer_id) GROUP BY ALL LIMIT 2000\nVISUALIZE 'which customer segment spends the most'" },
  { label: "Dashboard (3 intents)", sql: "SELECT date_trunc('month', order_date) AS order_month, region, channel, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'how are regions trending', 'which channel is biggest', 'where do region and channel combine best'" },
  { label: "Plain SQL (no clause)", sql: "SELECT * FROM products LIMIT 20" },
];
