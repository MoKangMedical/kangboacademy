# Production Merge Review - 2026-09-27

Status: merge baseline prepared and tested, NOT DEPLOYED. Baseline: 1.0.7-rc3. Subsequent candidate safety work is documented in FIRST_PRODUCT_ACCEPTANCE.md; the checks below describe this baseline unless explicitly updated.

## Preserved Production State

Production Git HEAD is b112bac; its working tree has 572 modified tracked files.
The 565 narration scripts and the unrelated course landing pages are not deployment targets.
Existing shuige, brain-training and zhangyiming navigation entries are retained in the updated homepage and core-course directory. Their destination files exist on the server.
The protected frontend/learn.html is not edited, included in the update set, or rolled back by this release.
Existing production audio and lesson bodies are untouched.

The baseline backend comparison retains all 86 routes and existing authentication/payment code. Later candidates add payment verification and practice retry protection. Deploy all reviewed backend helper modules together with main.py and the shared frontend manifest; main.py alone cannot start.

## Backup

Private server directory: /home/ubuntu/kangbo-backups/20260927T123850Z

- production-files.tar.gz: 1,279,109,118 bytes, 4,460 archive entries.
- SHA256: a7df7c37525e27220e005bc7f668c52b7a1e95162df10c5af54c21ed5fb9df46
- Includes frontend (including audio), backend source and data files; excludes virtual environments, dependency caches and raw database files.
- kangboacademy.db is a separate SQLite online backup, with integrity_check=ok.
- working-tree.patch and git-status.txt retain the production source modification inventory.
- This is a release-scope backup, not an OS image or full server disaster-recovery backup. Other databases and system configuration are not covered.

The backup is outside the public web root and protected by user-only permissions. Never publish it to GitHub or put it in a public download directory.

## Verification

- Local candidate suite: 178 tests (83 Node, 45 tooling Python, 50 backend Python).
- Server runtime: Python 3.12.3, FastAPI 0.136.1, Pydantic 2.13.3, Uvicorn 0.46.0.
- All 50 backend tests passed again in the server runtime; actual ASGI startup passed using disposable fixtures and a disposable database.
- A separate isolated process read real production course files: all 565 passed progress identity/file validation and nonempty article extraction (at least 200 HTML characters). This is not a pedagogical or copyright review.
- Real product configuration still yields 500 catalog rows and zero authorized purchasable product entries. Search links are not purchases.
- Desktop homepage (1365px) and mobile homepage/course directory (390px) have no page-level horizontal overflow; navigation retains all added links. Desktop navigation scrolls horizontally rather than wrapping labels. Mobile menu opens and fits the tested viewport.
- Production service and protected file hashes must be checked again immediately before deployment; a changed baseline stops the release.

## Deployment Scope And Rollback

1. Obtain owner approval for production deployment. Recheck disk space, live hashes, current database backup, and absence of a concurrently active release.
2. Stage ONLY the reviewed backend Python modules (not test files), frontend/index.html, frontend/courses.html, frontend/book-shop.html, shared manifest JSON and their JS dependencies from the verified candidate. New helper modules such as payment_security.py must be included. Upload new hash-named JS assets first, then HTML references. Never rsync --delete a complete source tree to production.
3. Verify the production process does not carry an unintended KANGBO_PROJECT_ROOT override. Test the candidate import in the actual environment, without touching production data. Keep subscription payment disabled; this release does not configure payment credentials or alter paid entitlements.
4. Install matched backend files and manifest, restart only kangboacademy.service, then verify local health and paced public checks. Confirm HTML cache revalidation and new hashed resource availability. Do not modify Nginx without a separately reviewed configuration change.
5. On failure, restore ONLY the overwritten code and HTML from the backup and restart the backend. New helper/assets may remain unused, or remove them only if recorded as newly created by this release. Do not restore the production database as a routine code rollback; preserve new user progress and orders. Do not roll back learn.html, lesson pages or audio.
6. Record the deployed hashes, health result and actual user-visible version. GitHub publication, source staging and unit tests are not deployment evidence.

## Remaining Restrictions

The production payment callback has pre-existing verification and state-protection gaps. Later local candidates add checks described in FIRST_PRODUCT_ACCEPTANCE.md; production remains unchanged. Real payment must not be enabled until the reviewed fixes are deployed and independently validated with the real merchant configuration.
Merchant authorization/product IDs, complete audio narration review, WeChat device validation, correct account login, filing and platform review remain separate release gates. This website merge does not publish a Mini Program.
