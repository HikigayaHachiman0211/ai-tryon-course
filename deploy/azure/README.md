# Azure VM release runbook

This directory is the single Azure course-demo deployment contract for the
three applications in this repository. It targets one AMD64 Ubuntu 24.04 VM,
Docker Compose, PostgreSQL 16, Azure Blob Storage, and Caddy. The architecture
is intentionally simple and low cost: the VM is a single point of failure and
does not have a platform SLA, but it is suitable for a university
demonstration.

The planned public surfaces are:

| Surface | Public URL | Compose upstream |
| --- | --- | --- |
| Main | `https://<fqdn>` | `main:8080` |
| Admin | `https://<fqdn>:8443` | `admin:8080` |
| Workbench | `https://<fqdn>:9443/static/index.html` | `workbench:8080` |

Only Caddy publishes ports 80, 443, 8443, and 9443. PostgreSQL and the three
application ports are reachable only on the ordinary Compose bridge network.
Port 80 is required for ACME validation and redirects to Main HTTPS. Caddy
uses the same FQDN on all three TLS ports; alternate-port certificate issuance
must be checked against the real endpoint, not just a parser.

## Cost and authorization boundary

The scripts never log in implicitly and never create a resource group until
`preflight.ps1` has checked an explicitly supplied subscription ID. The
operator must independently compare that ID with the Azure Portal
subscription blade and the Sponsorships portal, then pass
`-ConfirmAzureForStudents`. The CLI display name is not treated as proof of
the Azure for Students offer. Do not upgrade to Pay-As-You-Go, add a card, or
create Container Apps, AKS, ACR, managed PostgreSQL, Redis, Key Vault, Front
Door, Application Gateway, or other paid managed services.

The default cost guard is a conservative 30-day estimate of at most USD 25
and a remaining-credit reserve of at least USD 20. `preflight.ps1` requires
the current estimate, balance, credit expiry, and budget email as operator
inputs obtained outside Git. Free-service eligibility and invoice treatment
can differ from retail estimates. If the guard fails, stop before provisioning
unless the user explicitly approves a new threshold. `configure-cost-controls.ps1`
creates a monthly notification budget when the subscription API permits it;
budgets notify but do not automatically stop resources.

Use `az vm deallocate --resource-group <rg> --name <vm>` for planned downtime.
Deallocation stops compute charges, but the OS disk, public IP, and storage can
still incur cost. During active use inspect the sponsorship balance, storage
growth, Docker disk use, backup retention, and logs weekly; access the
subscription at least every 90 days and renew student eligibility annually if
eligible.

## Fresh deployment data decision

The default is a fresh course-demo database initialized by Admin and seeded
from the current `database.json` contract. The release gate requires exactly
4,721 product rows and the corresponding read models. The suspended GCP Cloud
SQL database is never read. `restore.ps1` accepts only a user-supplied,
checksum-verified PostgreSQL dump and restores it into a separately named
staging database before any controlled cutover; it never overwrites the
working database automatically.

Product assets are staged from the two repository image sources and uploaded
only from the verified manifest. The script rejects duplicate basenames with
different bytes. Product assets and browser-facing course media use anonymous
**Blob** read because the current UI consumes direct URLs; container listing is
not enabled. The `backups` container remains private. User photos, generated
results, Workbench uploads, and history use the course-media namespace with a
short/no-store cache policy. This is an explicit course-project compatibility
choice, not a commercial privacy design.

## Local release gate

Run from the repository root in PowerShell 7 where possible:

```powershell
pwsh -File deploy/azure/scripts/render-local-test-env.ps1
docker compose --env-file deploy/azure/.env.azure.test -f deploy/azure/compose.yaml config --quiet
az bicep build --file deploy/azure/infra/main.bicep
pwsh -File deploy/azure/scripts/package-release.ps1
```

The generated `.env.azure.test` and `infra/main.parameters.json` are ignored
and must not be committed. The test environment uses the local object-storage
adapter and test-only values; it is never a production credential source.
The final release package contains the ignored `database.json`, main/workbench
read models, all three locale resources, and the deployment files. It excludes
real `.env` files, keys, credentials, local databases, node modules, virtual
environments, user media, and prior archives. After packaging, the script
unpacks into a clean temporary directory and checks all three Docker build
contexts from inside that archive.

The full local command matrix is recorded by `package-release.ps1` and should
include:

```powershell
node scripts/i18n/check_resource_parity.mjs
node scripts/i18n/check_resource_parity.mjs --admin
node scripts/i18n/check_visible_literals.mjs --strict --all
python scripts/i18n/check_catalog_coverage.py
python scripts/i18n/sync_workbench_catalog.py --verify
Set-Location main-app/frontend; npm ci; npm run lint; npm run i18n-check; npm test -- --run; npm run build
Set-Location ../backend; python -m pytest app/tests -q; python -m compileall -q app
Set-Location ../admin/frontend; npm ci; npm run i18n-check; npm test -- --run; npm run build
Set-Location ../backend; python -m pytest -q; python -m compileall -q app
Set-Location ../../../tryon-workbench; npm ci; npm test -- --run; python -m pytest -q; python -m compileall -q .
```

The Workbench JavaScript package is a minimal pinned test package. Browser
tests must be run explicitly against a running release-like environment; an
unset E2E flag is not a valid skip.

## Provisioning sequence

1. Record the current Git status and resolve the repository root.
2. Run `preflight.ps1` with the exact student subscription ID, region,
   operator public `/32`, current cost evidence, budget email, credit expiry,
   and `-ConfirmAzureForStudents`.
3. Inspect the command output for SKU restrictions, quota, provider state,
   DNS/storage name availability, and cost thresholds. No resources are made
   before this point.
4. Run `provision.ps1`. It renders the ignored parameter file, runs
   `az deployment group what-if`, and requires `-ConfirmWhatIf` before the
   group deployment. Stop for any unexpected or destructive change.
5. Run `configure-cost-controls.ps1` and save only sanitized budget evidence.
6. Wait for cloud-init, then use `deploy.ps1` to transfer the checksum-verified
   archive, create the VM environment file with mode 0600, build images one at
   a time, start PostgreSQL, Admin, Workbench, Main, and Caddy, and enable the
   systemd unit. The normal path never uses `docker compose down -v`.
7. Run `upload-product-assets.ps1`, `upload-sample-models.ps1`, `smoke-test.ps1`,
   and the live acceptance matrix before claiming acceptance. The sample-model
   helper verifies hashes and refuses to replace existing different objects. The
   `-ContainerName` on both upload helpers must match `AZURE_PRODUCT_CONTAINER`
   when using a custom name.

The production environment file is `/opt/ai-tryon-course/shared/azure.env`.
It is not part of a release archive and is never printed. Generate database
passwords as URL-safe hex and generate the Fernet key with the installed
`cryptography` library; write them directly to the 0600 file instead of shell
history. Use the connection string path first for the course deployment and
test the managed-identity path separately before switching it on.

## Operations and recovery

`status.ps1` reports the VM power state, public endpoint status, Compose
health, disk/RAM, recent service errors, current release ID, and backup age
without reading secret values. `backup.ps1` creates a timestamped checksum
manifest containing a PostgreSQL custom-format dump, noncanonical persistent
application data, release metadata, image digests, and catalog manifests. It
never includes the environment file, keys, passwords, or private media.

`restore.ps1` first checks every checksum and PostgreSQL version, creates a
pre-restore backup, restores to an explicitly named empty/staging database,
runs schema and row-count checks, and restores one disposable application file.
Rehearsal cleanup is limited to the named staging resources.

`rollback.ps1` verifies the previous immutable release directory and its
checksums, refuses an incompatible database migration unless an approved
database restore is selected, switches only this Compose project, and reruns
health, TLS, i18n, and core smoke checks. It never deletes named volumes.

The Workbench task map is intentionally one replica and in memory. In-flight
tasks do not survive a Workbench process restart; uploads, assets, history,
Main history, Admin voice-clone files, PostgreSQL, and Caddy certificates are
on named persistent volumes. The systemd unit starts the current release
after Docker and the VM reboot.

## Troubleshooting guide

Every case below requires evidence first. Never disable TLS verification,
publish every port, run privileged containers, or replace production secrets
with defaults.

| Symptom | Evidence command | Safe fix / stop condition |
| --- | --- | --- |
| Disabled, expired, or exhausted student subscription | `az account show`; Sponsorships portal | Stop; renew/restore student eligibility or select an explicitly approved subscription. |
| Provider not registered, regional quota, or SKU restriction | `az provider show`; `az vm list-skus`; `az vm list-usage` | Register only Compute/Network/Storage or use the approved B2s fallback. Stop for paid upgrade or insufficient quota. |
| Bicep validation, name collision, DNS conflict, or public IP failure | `az bicep build`; `az deployment group what-if`; name-check commands | Correct parameters and rerun what-if. Stop on unexpected resources or destructive changes. |
| Cloud-init failed | `sudo cloud-init status --long`; `journalctl -u cloud-final` | Repair the idempotent bootstrap and rerun only after evidence; do not put secrets in cloud-init. |
| SSH denied or host-key warning | `az network nsg rule list`; `sudo ufw status`; `ssh -vv` | Update the exact caller `/32`, verify the host key out of band, and keep SSH closed globally. |
| Docker build OOM/full disk/unhealthy dependency | `free -h`; `df -h`; `docker system df`; `docker compose ps` | Build sequentially, clean only named unused artifacts, add swap, wait for health. Never delete volumes. |
| Vite URL still points to an old host | `docker compose config`; inspect built asset strings | Rebuild the frontend image with the three build-time URLs; runtime env edits cannot change Vite constants. |
| ACME, port-80, FQDN, alternate-port, redirect, or upload failure | `docker compose logs proxy`; `curl -v https://<fqdn>:8443/health` | Fix DNS/NSG/Caddy and body limits; require normal certificate verification on 443/8443/9443. Stop if all ports cannot get a public cert. |
| PostgreSQL auth/URI/migration/permission failure | `docker compose logs postgres admin`; `pg_isready`; `docker compose config` | Use URL-safe hex password, verify schema initialization and volume ownership. Restore only to staging first. |
| Blob 403, policy, connection, MIME/cache, Unicode, or CORS failure | `docker compose logs`; `az storage blob show`; HTTP `HEAD` | Check account/container policy, `Blob` read vs private backups, encoded object names, content settings, and only required CORS. |
| Missing catalog, empty fallback, 4,721 mismatch, double static prefix, image 404, or basename collision | `check_catalog_coverage.py`; asset manifest; HTTP image checks | Regenerate/read the exact ignored artifacts; reject collisions and rerun the full catalog gate. Never choose one collision arbitrarily. |
| AI 401/403/429, timeout, model retirement, malformed response, ASR/TTS denial | Admin provider status and sanitized service logs | Check provider/key/model/quota and bounded retries. A real external failure blocks live acceptance; mocks do not pass. |
| CORS, mixed content, postMessage origin, stale URL, or microphone failure | Browser console/network; exact origin tests; HTTPS microphone permission | Use the three exact origins and HTTPS. Never use `*` for bridge messages or CORS credentials. |
| Workbench task lost, persistent path missing, or polling timeout | `docker compose ps`; volume mounts; Workbench logs | Keep one replica, mount the three named volumes, and report in-flight-task loss after restart as the documented limitation. |
| Missing/stale locale, wrong `Content-Language`, or cross-app language loss | root i18n gates; browser URL/localStorage; response headers | Fix resource parity, mounted-state relocalization, and `lang` propagation; do not mark the locale gate passed on a single page. |

## Stop conditions

Stop and report rather than improvising if the subscription/offer is wrong or
disabled, the approved SKU is unavailable without cost approval, what-if has
unexpected resources, release contexts cannot build from a clean archive,
required product artifacts are missing, required AI credentials are absent,
TLS fails on a required public port, a destructive migration is proposed, or a
required live workflow still fails after bounded diagnosis.

The final evidence report must distinguish `DEPLOYED AND ACCEPTED`,
`IMPLEMENTED BUT NOT PROVISIONED`, and `BLOCKED`. It must include sanitized
subscription/region/VM/FQDN/release information, changed files, inventory,
test and live matrices, 4,721/catalog/image counts, all three locale results,
provider/voice evidence, restart/backup/restore/rollback evidence, budget
status, and exact limitations. Do not claim “fully deployed,” “all functions
work,” or “zero bugs” without the corresponding evidence.
