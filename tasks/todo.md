# Task Review

- [x] Inspect the existing similar-player lookup and market-stats schema.
- [x] Add selectable peer matching by market value or purchase/sales ratio.
- [x] Add pure helper tests for both matching modes and invalid configuration.
- [x] Run focused tests, non-integration tests, Ruff lint, and Ruff formatting.

## Review

- The Market Trends lookup now supports `Value` and `Purchase/sales ratio` matching.
- The tolerance is relative to the selected anchor metric, and peers are ranked by closest distance on that metric.
- The anchor is excluded and missing selected metrics are ignored.
- Verification: `151 passed, 6 deselected`; Ruff check and format check passed.
- Full pytest still has two unrelated integration failures because live `scoring_system` values are lowercase `sofascore` while tests expect `SofaScore`.
