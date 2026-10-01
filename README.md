# Kangbo Academy

Source release: `1.0.7-rc6`. The website and backend were deployed on 2026-10-01 after server-runtime verification. Mini Program validation and platform release are tracked separately; a repository update is not a WeChat approval receipt.

## Source Layout

- `shared/content-contract.json`: shared metadata for 65 core courses and 500 book courses.
- `kangboacademy-miniapp/`: WeChat Mini Program source and tests.
- `server_index.html`, `server_patch/frontend/`: website update source.
- `server_patch/backend/`: backend migration candidate; compare with the current production backend before deployment.
- `tools/`: validation, content synchronization, merchant import and delivery tooling.
- `docs/DELIVERY.md`: verification, release gates and rollback requirements.

The 2026-10-01 release adds learning recovery and retry protection, payment signature verification, a Mini Program-compatible shared catalog module, local D3 assets, and a mobile book-course layout fix. The local suite passed 226 tests; the server passed 79 backend tests, 11 isolated API checks and content extraction checks for all 565 courses. Real merchant goods and payment activation remain pending.

Production lesson bodies, audio, user databases, credentials and merchant authorization documents are intentionally excluded. Product-search links are not verified purchasable products. The merchant mapping template remains unfilled until genuine authorization and product identifiers are provided.

Website and Mini Program changes share one metadata contract but have separate frontend implementations. Generate and validate the contract with `python3 tools/build_content_contract.py --check`; see `docs/DELIVERY.md` for all test commands.

Do not deploy `server_patch/backend/main.py` over a newer production file without reviewing and merging differences. Do not infer successful payment, filing, submission or release from local test success.
