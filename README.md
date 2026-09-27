# Kangbo Academy

Source candidate: `1.0.7-rc2`. This repository is not evidence of a production deployment or WeChat approval.

## Source Layout

- `shared/content-contract.json`: shared metadata for 65 core courses and 500 book courses.
- `kangboacademy-miniapp/`: WeChat Mini Program source and tests.
- `server_index.html`, `server_patch/frontend/`: website update source.
- `server_patch/backend/`: backend migration candidate; compare with the current production backend before deployment.
- `tools/`: validation, content synchronization, merchant import and delivery tooling.
- `docs/DELIVERY.md`: verification, release gates and rollback requirements.

Production lesson bodies, audio, user databases, credentials and merchant authorization documents are intentionally excluded. Product-search links are not verified purchasable products. The merchant mapping template remains unfilled until genuine authorization and product identifiers are provided.

Website and Mini Program changes share one metadata contract but have separate frontend implementations. Generate and validate the contract with `python3 tools/build_content_contract.py --check`; see `docs/DELIVERY.md` for all test commands.

Do not deploy `server_patch/backend/main.py` over a newer production file without reviewing and merging differences. Do not infer successful payment, filing, submission or release from local test success.
