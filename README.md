# Jev demos

Small, self-contained demos of [TypeSafe](https://typesafe.ai)'s **Jev**, a System One model
that returns typed judgments (probabilities, choices, scores) instead of generated text. Each
demo puts Jev inside a tool data and analytics engineers already use, and each one is scored
honestly: live vs simulated is always labelled, and numbers come from logged runs.

| # | Demo | What it shows |
|---|------|---------------|
| 01 | Cringe-o-Meter | *coming soon* |
| 02 | semsql | *coming soon* |
| 03 | VISUALIZE | *coming soon* |
| 04 | [dbt semantic tests](04-dbt-semantic-tests/) | dbt tests written as English sentences catch rows that pass every structural test but are still wrong (or leak PII), scored against a hidden answer key and a regex baseline |

Every demo lives in its own folder with its own README, dependencies and instructions. Most run
without an API key in a clearly labelled `SIMULATED` mode; put `TYPESAFE_API_KEY=...` in the
demo folder's `.env` for live results.

What changed and when: [CHANGELOG.md](CHANGELOG.md).

Built by [DataGobes](https://datagobes.dev).

## License

[MIT](LICENSE) — covers every demo in this repo.
