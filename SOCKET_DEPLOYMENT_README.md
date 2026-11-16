# Isolated Schwab read-only Unix socket integration

## Scope and safety

This replacement includes the **entire uploaded project**, plus a read-only local socket transport and a new `socket_service.py` entry point. The socket accepts only `stock_quote` and `option_chain` for SPY/QQQ/IWM, validates each request, verifies the Linux peer UID is `ubuntu`, and dispatches under the canonical `/var/lib/schwab-worker/schwab-market-data.lock` lock as the dedicated `schwab-worker` account. The service has **no brokerage order request type**.

**Not implemented:** automated classification-to-paper-trade execution, persistent stop monitoring, verified Discord message identity, or live order placement. Nothing here enables those features. A successful quote retrieval does **not** imply a fresh market quote during closed hours.

The socket code, unit, and policies are provided but **are not installed by replacing your Mac project files**. Do not directly overwrite `/opt/my-trading-simulator-schwab` with the whole app tree: that directory has strict ownership and contains isolated market-data code. Do not copy `.env`, OAuth JSON, AWS certificates, private keys, or database files.

## 1. Mac: preserve and test

Keep a backup of your existing project and reconcile uncommitted files before copying the replacement over it. This ZIP was assembled from the `my-trading-simulator-current.zip` you supplied, so any files not included in that upload are not available here. The ZIP does not include the ignored local OAuth token or `.env`.

In Mac Terminal:

```bash
cd ~/Documents/PythonAI/my-trading-simulator
python -m pytest -q
git status --short
git diff --check
```

The uploaded baseline was reported as **492 passed** on the Mac. This release adds **5 socket-service/lifecycle tests**, so the expected full count is **497** if the installed dependencies and same tests are present. On the build container, `schwab-py` is missing; 452 non-Schwab-dependent tests passed, including all 56 socket tests. Do not interpret this as 497 verified in the build container.

Stage only reviewed source, tests, and deployment files, then commit and push; leave the existing untracked documentation files alone unless you deliberately want to commit them.

## 2. AWS main project: after pushing to GitHub

```bash
cd /home/ubuntu/my-trading-simulator
git status --short
git pull --ff-only origin main
source .venv/bin/activate
python -m pytest -q
```

Do not restart the existing API/classifier just to enable market-data IPC. Keep `execution_allowed=False` and live brokerage orders disabled.

## 3. Update only the isolated worker's socket modules

Run in AWS SSH **after** testing the repository update. This does not touch tokens or private keys. Existing source modules in the isolated worker must remain present (including `schwab_client.py`, `schwab_market_data_worker.py`, and `secrets_manager.py`).

```bash
set -e
ROOT=/home/ubuntu/my-trading-simulator/app/my_trading_simulator/market_data
DEST=/opt/my-trading-simulator-schwab/app/my_trading_simulator/market_data
for name in socket_protocol.py socket_dispatcher.py socket_client.py socket_handler.py socket_server.py socket_peer_auth.py socket_directory_security.py socket_service.py; do
  sudo install -o root -g schwab-worker -m 640 "$ROOT/$name" "$DEST/$name"
  sudo cmp "$ROOT/$name" "$DEST/$name"
done
sudo stat -c '%U:%G %a %n' "$DEST/socket_service.py"
```

The socket interface server's service account is `schwab-worker`, and only it can read protected token storage under `/var/lib/schwab-worker` (mode 700). `ubuntu` is permitted to communicate through the separate group-owned socket directory, not to read tokens.

## 4. Install runtime-directory rule and the optional systemd service

Before proceeding, verify that the `schwab-worker` account and `trading-market-data` group already exist; `ubuntu` and `schwab-worker` should be members of that group. Your prior AWS setup established this.

```bash
cd /home/ubuntu/my-trading-simulator
sudo install -o root -g root -m 644 \
  deploy/systemd/my-trading-simulator-market-data.tmpfiles.conf \
  /etc/tmpfiles.d/my-trading-simulator-market-data.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/my-trading-simulator-market-data.conf
sudo stat -c '%U:%G %a %n' /run/my-trading-simulator-market-data
sudo install -o root -g root -m 644 \
  deploy/systemd/my-trading-simulator-market-data.service \
  /etc/systemd/system/my-trading-simulator-market-data.service
sudo systemctl daemon-reload
```

Expected directory: `schwab-worker:trading-market-data 2770`. The unit is **not enabled** by these commands. Note: the runtime directory is recreated after reboot by `systemd-tmpfiles`; the service is not automatically enabled.

Run the **no-Schwab** configuration check first (no OAuth reads, quotes or brokerage calls):

```bash
cd /var/tmp
sudo -u schwab-worker env \
  HOME=/var/lib/schwab-worker \
  PYTHONPATH=/opt/my-trading-simulator-schwab/app \
  /opt/my-trading-simulator-schwab/.venv/bin/python -m \
  my_trading_simulator.market_data.socket_service --check-config
```

## 5. Manual, controlled read-only connectivity check

**Only after** the Mac and AWS test suites pass and `--check-config` succeeds, optionally start the worker to test stock quote requests:

```bash
sudo systemctl start my-trading-simulator-market-data.service
sudo systemctl status my-trading-simulator-market-data.service --no-pager
sudo stat -c '%U:%G %a %n' /run/my-trading-simulator-market-data/schwab.sock
```

The socket should have mode 660 and the dedicated `trading-market-data` group. On AWS, your current SSH shell may have old group membership; use `sudo -u ubuntu` to obtain freshly initialized groups, or reconnect via SSH.

```bash
sudo -u ubuntu env \
  PYTHONPATH=/home/ubuntu/my-trading-simulator/app \
  /home/ubuntu/my-trading-simulator/.venv/bin/python - <<'PY'
from my_trading_simulator.market_data.socket_client import MarketDataSocketClient
quote = MarketDataSocketClient(timeout_seconds=10).get_stock_quote('SPY')
print('Read-only SPY market-data response:', isinstance(quote, dict), 'SPY' in quote)
PY
```

This invokes a real read-only Schwab API call, requires a valid OAuth token and AWS IAM Roles Anywhere credentials, and may refresh the OAuth access token. No brokerage order is submitted. Stop the optional service after the test if you do not want it left running:

```bash
sudo systemctl stop my-trading-simulator-market-data.service
sudo systemctl is-active my-trading-simulator-market-data.service
```

**Do not enable/start this automatically** before explicitly reviewing the production deployment behavior. The API/classifier remain independent, dry-run only.

## Troubleshooting and manual recovery

- `--check-config` fails: check the process is `schwab-worker` and `/run/my-trading-simulator-market-data` is a real directory owned by `schwab-worker:trading-market-data` with mode `2770`. Do not chmod or chown private OAuth storage to make the check pass.
- Socket unavailable: check `sudo journalctl -u my-trading-simulator-market-data.service -n 80 --no-pager` (do not paste secrets). Stop the service and check its exit state.
- **Stale socket after crash**: the server intentionally refuses to overwrite a socket path. Confirm the service is stopped and **no process is listening**, and that the file is a socket at the expected path. Only then remove that one stale socket file as the privileged operator. Never delete/recreate the OAuth lock file to resolve this; lock inode replacement can break mutual exclusion.
- The server only authorizes the Linux `ubuntu` UID. A different account will receive a closed connection. The Linux `ubuntu` account has sudo privileges on this Lightsail host, so this is meaningful isolation against ordinary unprivileged processes, **not a sandbox against a compromised privileged host administrator**.
- Requests are bounded in size. An oversized option chain response fails closed rather than returning partial data; no trade should be inferred from such a failure.
- If a socket service stop is requested during a slow Schwab request, the signal sets a shutdown flag; service stop is processed once the current sequential operation completes, subject to systemd stop timeout.
- Do not deploy this source tree to the dedicated worker as writable `ubuntu`-owned files. Preserve `root:schwab-worker 640` module permissions.
