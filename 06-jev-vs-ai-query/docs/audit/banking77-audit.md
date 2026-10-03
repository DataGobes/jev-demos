# Banking77 label audit (post-hoc, 2026-10-03)

The question: some of the judges' "misses" and "false alarms" on Banking77 might be the dataset's
fault, not the judge's. Banking77 is known to be noisy. Ying and Thomas
([Label Errors in BANKING77](https://aclanthology.org/2022.insights-1.19), 2022) estimate that about
14% of its training utterances may be mislabelled.

**This is a side analysis.** It was done after the runs, by Claude reading the queries, at the user's
request. It does not change the frozen key (`eval/banking77_swaps.csv`) or any logged score. The
judgments it reads are the ones in the table after pass 2 (`--fresh`), which reproduce pass 1 within
0.01 on Banking77. The verdicts per row are in [`banking77_audit.csv`](banking77_audit.csv) (ids,
intents and a reason, no query text).

## What was reviewed

- All 75 near-miss swaps, plus the 20 random swaps that at most one judge flagged: is the planted
  label really wrong?
- The 27 un-swapped rows that at least two of Jev, gpt-oss-20b and Llama 3.3 70B flagged, or that Jev
  flagged: is the original label wrong?

## What it found: 34 of the 2,000 rows are debatable

| kind | rows | example |
|---|---|---|
| swap fixes an original error | 2 | "tried to buy something online … declined", originally `declined_transfer`, swapped to `declined_card_payment` |
| swap where both labels fit | 11 | "I don't think I received the correct amount of cash in my ATM transaction", `wrong_exchange_rate_for_cash_withdrawal` swapped to `wrong_amount_of_cash_received` |
| original label clearly wrong | 3 | "Someone stole my cards!" labelled `lost_or_stolen_phone` |
| original label questionable | 18 | nine "where is my PIN" questions labelled `get_physical_card` (a dataset convention) |

The other 62 near-miss swaps and the other 19 reviewed random swaps are real errors. The rest of the 27 flagged
clean rows (6) carry correct labels that the judges misread, for example "Can I top up using my
car?", which is a typo for card.

## Effect on the scores (as keyed, then with the 34 rows removed)

| judge | F1 as keyed | precision | F1 without the 34 | precision | recall |
|---|---|---|---|---|---|
| Jev | 0.56 | 0.83 | 0.62 | 0.98 | 0.45 |
| gpt-oss-20b | 0.66 | 0.55 | 0.71 | 0.59 | 0.87 |
| Llama 3.3 70B | 0.50 | 0.51 | 0.53 | 0.54 | 0.51 |

- Label noise explains almost all of Jev's false alarms: 12 of its 13 sit on debatable original
  labels. Without them its precision is 0.98.
- It doesn't explain Jev's low recall. Near-miss recall moves only from 0.25 to 0.29. Jev misses
  mostly clear swaps, and gives them a middling probability: the median p on a missed swap is 0.42.
- The ranking doesn't change. gpt-oss-20b still leads on Banking77.

## Jev's threshold (post-hoc, not pre-registered)

The test flags at `p >= 0.8`. On the same judgments, as keyed:

| threshold | precision | recall | F1 |
|---|---|---|---|
| 0.8 (as run) | 0.83 | 0.42 | 0.56 |
| 0.7 | 0.76 | 0.48 | 0.59 |
| 0.6 | 0.70 | 0.55 | 0.62 |
| 0.5 | 0.64 | 0.63 | 0.64 |

At 0.5, Jev comes within 0.02 of gpt-oss-20b's F1 (0.66). This threshold was picked after seeing the
results, so it's a hint about tuning, not a result.
