# Cloud workstation (AWS): runbook

*Prepared 2026-11-26 (T-27). Nothing is created yet: every script in
`scripts/cloud/` prints a plan until it is run with `APPLY=1`.*

**Why.** The owner works from China over a VPN through a home Raspberry Pi.
Today the agents' API traffic (~2.5 Mbit/s up), every Street View download and
every Google call go through that line. A small EC2 box in Frankfurt fixes that:

- Claude Code sessions run there and talk to Anthropic directly.
- Images come from Google straight into AWS.
- The owner's line carries only a terminal or the phone app.

Frankfurt (`eu-central-1`) also sits next to Neon.

## Decisions

| | Choice | Why |
|---|---|---|
| Instance | **m7i.xlarge** (4 vCPU, 16 GB, x86) | Several Claude sessions + PostGIS + Vite/pytest + DINOv2-small on CPU. x86, because `postgis/postgis` has no arm64 image. |
| GPU | none by default | RQI inference and the SVR head are CPU-friendly (a full rescore is ~1 h on 4 vCPU). For a big feature re-extraction, stop the box and switch to `g4dn.xlarge` (T4). That needs NVIDIA drivers or a Deep Learning AMI, which this runbook doesn't cover. |
| OS | Ubuntu 24.04 LTS | Supported by Claude Code; SSM agent preinstalled. |
| Access | **SSM Session Manager only** | The security group has **no inbound rules**: no SSH port, no key pair, no public service. |
| Secrets | SSM Parameter Store (SecureString) | Never in git, user-data, AMIs or the shell history. The instance role reads only `/smooth-route/*`. |
| Code | read-only GitHub deploy key; work comes back as a **git bundle via S3** | Keeps the team rule "never push": the box can't write to GitHub at all. |
| DB | PostGIS in Docker on the box, **one writer at a time** | A `db-primary` marker in S3 decides who owns it. A handover is a 2.5 MB `pg_dump`. |
| Data transfer | throttled S3 sync from the Mac, once, overnight | Images exist only on the Mac; re-fetching them from Google would cost quota. |
| Neon | never on the box | `publish.py` stays on the Mac (docs/RELEASE.md). |

## Cost (eu-central-1, on-demand, Nov 2026, approximate: check the AWS pricing page)

| Item | Rate | 6 h/day (≈180 h) | 24/7 |
|---|---|---|---|
| m7i.xlarge | ~$0.24/h | ~$43 | ~$176 |
| g4dn.xlarge (if switched) | ~$0.66/h | ~$119 | ~$480 |
| Public IPv4 (needed for outbound without a NAT) | $0.005/h while running | ~$1 | ~$4 |
| 60 GB gp3 disk (billed while stopped too) | ~$0.095/GB-mo | ~$6 | ~$6 |
| S3, ~1.5 GB + 30 days of old versions | ~$0.025/GB-mo | <$0.10 | <$0.10 |
| Traffic out (Claude API, git, sync down to the Mac) | ~$0.09/GB | ~$1 | ~$2 |

**Typical: ~$50/month at 6 h/day.** Spot pricing is about half, but the box can be
reclaimed mid-session, so it's not worth it here. Three automatic stops keep the
bill bounded:

1. **Idle alarm:** CloudWatch stops the box after average CPU < 3% for 60 min.
2. **Uptime cap:** a timer on the box powers it off after 14 h unless
   `~/keep-awake` was touched in the last 2 h.
3. **Budget alert:** an AWS Budget (`BUDGET_EMAIL=…`, $40/month) e-mails at 80%
   actual and 100% forecast.

"Stop" keeps the disk and ends compute billing. Only `teardown.sh` deletes anything.

## One-time setup (owner, ~30 min + an overnight upload)

On the Mac, with the `i` CLI profile:

1. **Plugin:** `brew install --cask session-manager-plugin`.
2. **Local Google key.** Create a separate *local* key (Street View Static +
   Metadata, Directions, Geocoding), the one from SECURITY.md item 2. It is not
   the Vercel server key.
3. **Deploy key:** `ssh-keygen -t ed25519 -f /tmp/ws_deploy -N ''`. Add
   `/tmp/ws_deploy.pub` under GitHub → repo → Settings → Deploy keys, **write
   access off**.
4. **Secrets:** `APPLY=1 scripts/cloud/put-secrets.sh` (input hidden). Then
   `rm /tmp/ws_deploy*`.
5. **Plan, then create.** Review `scripts/cloud/create.sh` (plan only), then run
   `APPLY=1 BUDGET_EMAIL=<you> scripts/cloud/create.sh`.
   - It creates: a private, encrypted, versioned S3 bucket; the IAM role (SSM
     core + its own parameters + its own bucket); a no-inbound security group;
     the instance (IMDSv2 only, encrypted disk); the idle alarm; the budget.
   - The bootstrap (`bootstrap.sh` as user-data) then installs Docker, PostGIS,
     git, tmux, Node 22, uv, the CPU torch venv (same pins as the Mac, so
     `rqi_model.joblib` loads), `npm ci` and Claude Code. It takes ~10 min; log at
     `/var/log/smooth-route-bootstrap.log`.
6. **Overnight upload:** `caffeinate -i env APPLY=1 scripts/cloud/sync.sh mac-push`.
   - It sends about 1.4 GB (`data/` without backups/static, the untracked
     `ml/cache` files, a DB dump) at **120 KB/s**, about 40% of the uplink: ~3 h.
     Later runs send only changes.
   - It hands the DB to the box; don't write to the local DB until `mac-pull`.
7. **On the box:** `APPLY=1 scripts/cloud/ws.sh connect`, then
   `sudo -iu ubuntu`, `cd smooth-route`, `APPLY=1 scripts/cloud/sync.sh ws-pull`
   (fast, in-region).

## Claude Code on the box (owner, once per login)

1. **Log in.** In the SSM shell, as `ubuntu` (never root), `cd ~/smooth-route` and
   run `claude`.
   - It offers a login URL: press `c` to copy it and open it on the phone or Mac.
     If a code appears, paste it back.
   - Credentials land in `~/.claude/.credentials.json` (0600). Check expiry with
     `claude auth status --text`.
   - Use the **subscription login**. `claude setup-token` / an API key can't run
     Remote Control. Leave `ANTHROPIC_API_KEY` and
     `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` unset; the latter disables
     Remote Control.
2. **Trust the repo.** Answer the workspace-trust prompt once interactively, then
   exit.
3. **Start Remote Control** in tmux so it survives the SSM disconnect:
   `tmux new -d -s rc 'claude remote-control --name smooth-route-ws'`.
4. **Connect from the phone:** Claude app → **Code** → the `smooth-route-ws`
   session (green dot). `claude remote-control --continue` resumes after a
   restart. Permission prompts arrive on the phone.
   - Keep the normal permission modes. Don't use `--dangerously-skip-permissions`:
     the box holds the Google key.
   - The transcript passes through Anthropic; files and commands stay on the box.

## Daily use

- **Start / stop / status:** `APPLY=1 scripts/cloud/ws.sh start|stop|status` from
  the Mac, or the AWS Console app on the phone.
- **After a boot:** reattach with `ws.sh connect` → `sudo -iu ubuntu` →
  `tmux attach -t rc`, or start Remote Control again.
- **Long job:** `touch ~/keep-awake` (and again every < 2 h). A CPU-bound job
  keeps the idle alarm off by itself.
- **Collections:** run them on the box. Google → AWS directly; the quota counter
  (`data/quota`) travels with `data/`.
- **Bringing work home:**
  - On the box: `sync.sh ws-bundle` (claude/* branches).
  - On the Mac: `sync.sh mac-fetch`, then review `refs/remotes/cloud/claude/*`
    and merge as usual.
  - Data and DB: `ws-push` on the box, then `mac-pull` on the Mac (throttled; the
    local DB is backed up first).

## Teardown

1. **Bring everything home:** `ws-bundle` + `ws-push` on the box, then
   `mac-fetch` + `mac-pull` on the Mac.
2. **Remove the box:** `APPLY=1 scripts/cloud/teardown.sh` removes the instance
   and its disk, the alarm, the budget, the SG and the IAM role.
   - Add `DELETE_DATA=1` to delete the bucket (empty it in the S3 console first)
     and `DELETE_SECRETS=1` to delete the parameters.
   - Then delete the deploy key in GitHub.

## Security notes

- **Exposure:** nothing listens on the internet. Dev servers (:8000/:5173) and
  PostGIS (:5433) bind on the box, but the security group has no inbound rules.
  To see the UI, use SSM port forwarding, which goes over the owner's line:
  `aws ssm start-session --target <id> --document-name AWS-StartPortForwardingSession --parameters portNumber=5173,localPortNumber=5173`.
- **Instance role:** it can read `/smooth-route/*` parameters and read/write its
  own bucket. It **cannot** list or delete other AWS resources, read other
  parameters or delete objects; versioning undoes overwrites for 30 days.
- **What a compromised box exposes:**
  - It holds the local Google key, which the per-API quotas cap (SECURITY.md item 3).
  - It holds the read-only deploy key and the Claude login.
  - It has no Neon credential, no Vercel token and no AWS keys of the owner.
- **Owner's `i` profile:** used only on the Mac to run these scripts. Never copy
  it to the box.
