# my-trading-simulator — full-source replacement and AWS deployment notes

## What this ZIP is

This ZIP contains a **complete source tree** based on the user's uploaded Git archive (commit `5dc19c4` in the supplied context) with narrowly scoped safety and operator fixes. It is **not** an automated production deployment and contains no running service state. There are no API keys, OAuth tokens, SSH keys, AWS certificates, `.env`, SQLite databases, `venv`, or `.git` history.

**Live brokerage order execution is not enabled.** Notification classifications are stored with `execution_allowed=False`. No classifier-to-paper-trade bridge is activated in this release.

## Fixes included

1. **Fail-closed Schwab option-chain parsing** — reject malformed/non-finite prices, invalid strikes, malformed expiration groups, missing symbols, bad volume, booleans, and malformed individual option entries. Continue evaluating safe candidates instead of crashing a whole selection on a bad entry. Exact strike / symbol matching remain exact.
2. **Option quote hardening** — explicitly reject zero/negative/non-finite bids and asks; verify timezone-aware `now` before comparing timestamps; retain stale-quote and spread rules.
3. **AWS Secrets Manager working-directory fix** — with `MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE=aws` explicitly configured, do not call implicit `load_dotenv()`, which could fail when the dedicated `schwab-worker` cannot traverse `/home/ubuntu`. Local development still supports `.env` discovery. Approved AWS profile selection and no-credential-fallback remain unchanged.
4. **Read-only notification audit** — `python -m my_trading_simulator.observability.notification_audit` reports counts, pending IDs, possibly stuck `PROCESSING` IDs, action totals, and unexpected execution authorization without printing message bodies, credentials, or OAuth tokens. It does **not** retry any records or touch the brokerage.
5. **Regression tests** — tests for all of the above (24 new tests).

## Tests performed on the provided ZIP

- **438 passed** using test-only import stubs for unavailable OpenAI and schwab-py SDKs. The stubs were only placed in the temporary test environment and are **not included** in the ZIP. This validates project logic under mocks but is **not a substitute for full dependency integration tests**.
- **402 passed** directly with available dependencies, excluding tests that need the unavailable SDK packages.
- The original project reported 414 passing tests on the owner's Mac before these changes. Run the full suite on Mac and AWS with real dependencies before deploying.
- No live API requests or end-to-end iPhone notifications were exercised during this ZIP build.

## Before replacing any existing checkout

**Do not unzip over a checkout with uncommitted changes without backing them up.** The owner previously had uncommitted modifications in `schwab_auth.py`, `schwab_test_options.py`, `schwab_test_quotes.py`, and untracked documentation files. This ZIP reflects the uploaded committed snapshot and will not include those uncommitted changes.

On Mac:

```bash
cd ~/Documents/PythonAI
mkdir -p my-trading-simulator-replacement
unzip -q /path/to/my-trading-simulator-fixed-complete.zip -d my-trading-simulator-replacement
cd my-trading-simulator-replacement
python -m pip install -e '.[dev]'
# The API import tests require a 32+ character test token on a developer machine.
export NOTIFICATION_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m pytest -q
```

`unzip` produces a source tree, not a ready-to-run AWS service. After tests pass, review the code diff against your existing Git checkout and commit the changes. Do **not** overwrite real `.env`, `.aws`, OAuth, or DB files.

## AWS deployment requirements

1. Verify and back up `data/trading_simulator.db` consistently (stop writes or use SQLite's backup API; do not copy a live WAL DB naively).
2. Transfer reviewed source via Git or a verified archive. Run `python -m pytest -q` in the actual AWS virtual environment.
3. Existing services: `my-trading-simulator-api.service`, `my-trading-simulator-classifier.service`. Restart only after a verified upgrade; restarting the classifier **deliberately skips its pre-startup backlog**. Do not silently reclassify old 0DTE alerts.
4. The isolated `schwab-worker` runs its own copy under `/opt/my-trading-simulator-schwab/app/my_trading_simulator`. Copy code there only after review, maintaining `root:schwab-worker` ownership and 0750 directories / 0640 source files. Its protected token stays `/var/lib/schwab-worker/schwab_token.json` (0600). The worker's working directory must be accessible to its OS account.
5. Run the read-only queue audit from the main AWS project root:

```bash
cd /home/ubuntu/my-trading-simulator
python -m my_trading_simulator.observability.notification_audit
```

This command must never be wired to process/retry failed notifications.

## Integration still not complete (deliberately NOT enabled)

- **iPhone forwarding**: real Casey Discord notification ingestion remains unverified. A notification title matching `Casey` is not cryptographic proof that the author is Casey. The API bearer token verifies the sender of the HTTP request, not the original Discord author's identity.
- **Structured trading intent**: the current persisted classification lacks explicit strike, OCC contract symbol, size, and exit fraction; `context=None` is still passed to the classifier. No authenticated Discord message identity/context is available for automatic action.
- **Market-data isolation**: Schwab read-only quotes work in manual AWS tests, but no persistent, approved IPC channel currently connects the protected Schwab account to the paper-trade coordinator.
- **Paper coordinator**: no automatic, idempotent, safety-reviewed path connects classification, quote validation, contract identity, market-session checks, paper fill, and status reconciliation.
- **Unattended stops/alerts**: stop monitor is currently single-cycle; exchange holidays, persistent alert handling, and restart recovery need implementation before unattended use.
- **OAuth**: Schwab interactive reauthorization still periodically required. Access-token refreshing is implemented by the existing protected local token store, but AWS rotation/recovery monitoring is not a complete unattended system.
- **Live brokerage trading**: remains disabled. Do not add order endpoints, broker execution permissions, or direct routes from LLM classification to broker orders.

## Safe migration sequence

1. Review and test the replacement on Mac, preserve any local modifications.
2. Review a Git diff; push approved changes with a commit hash.
3. Deploy to AWS main application, execute the full test suite, and check the notification audit.
4. Update the isolated Schwab worker copy **only if needed** for its source modules and permissions.
5. Validate both systemd units and read-only quote/chain calls. Do not enable a paper-fill integration until the above provenance, idempotency, and trade-context gaps are resolved.
