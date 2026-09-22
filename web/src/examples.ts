// Chosen for signal, not coverage: each example answers its question at a glance
// (measured spreads: LATAM 0.37x vs 1.2-1.7x; Electronics 72x Books on revenue but
// third on profit; price/rating r=+0.83; December spikes at 1.8x median). Channel
// data was dropped entirely - its totals sit within 1.03x on every measure.
// 3 -> 4 is deliberate: "Electronics is 80% of revenue", then "...but Home earns
// the most profit", with the identifier trap firing quietly on the second one.
export const EXAMPLES: { label: string; sql: string }[] = [
  { label: "Regions trending", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'how are regions trending'" },
  { label: "Same query, different question", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'which region sold the most overall'" },
  { label: "Category share", sql: "SELECT category, sum(revenue) AS revenue FROM orders JOIN products USING (product_id) GROUP BY ALL\nVISUALIZE 'what share of revenue comes from each category'" },
  { label: "Identifier trap", sql: "SELECT category, product_id, sum(profit) AS profit\nFROM orders JOIN products USING (product_id) GROUP BY ALL\nVISUALIZE 'which category is the most profitable'" },
  { label: "Price vs rating", sql: "SELECT price, rating, category FROM products\nVISUALIZE 'do more expensive products get better ratings'" },
  { label: "Price distribution", sql: "SELECT price, rating FROM products\nVISUALIZE 'what price range do most products fall in'" },
  { label: "Dashboard (3 intents)", sql: "SELECT date_trunc('month', order_date) AS order_month, category, sum(revenue) AS revenue, sum(profit) AS profit\nFROM orders JOIN products USING (product_id) GROUP BY ALL\nVISUALIZE 'how is total revenue trending', 'which category brings in the most revenue', 'which category earns the most profit'" },
  { label: "Plain SQL (no clause)", sql: "SELECT * FROM products LIMIT 20" },
];
