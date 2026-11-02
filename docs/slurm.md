# Slurm backend scaffold — disabled, offline only

This is an administrator-side adapter, **not an enabled workbench execution mode**. No Slurm code is imported by `backend/app.py` or `backend/jobs.py`; no route, backend selector or SSH administration endpoint has been added. The local xTB backend and UI remain independent.

## Files and blank settings

- `config/slurm.example.json`: complete sample, `enabled: false`; SSH alias, remote root, partition/account, CPU/memory/time, executable, environment setup and optional site submission preamble are blank/null.
- `.private/slurm.json`: initialize locally with tools/init_config.py, mode0600; never served. Only an administrator may edit it. The adapter rejects an unsafe owner/mode or symlink and unknown/missing keys. It never reads existing SSH configuration or keys to infer settings.
- `templates/slurm.sbatch.in`: reviewable batch template. Resource/job-name/workdir/output settings are generated as fixed `sbatch` argv, not user-controlled `#SBATCH` lines. `site_preamble` and `environment_setup` are trusted administrator Bash, intentionally blank. They are not accepted from molecule/API requests. They are written to a private remote job script, so do not embed secrets.
- `backend/slurm.py`: `Config`, `SSHTransport`, `SlurmAdapter` methods `connection`, `submit`, `get`, `status`, `cancel`, `artifact`, `collect`.
- `backend/slurm_remote.py`: fixed Python helper for private-directory staging and allowlisted bounded retrieval.
- `tests/test_slurm.py`: offline mocks and local temporary-filesystem helper tests only.

Blank or disabled configuration reports `connected:false` and raises `Unavailable` before any transport call. Even complete configuration reports no proven connection: construction/configuration is not a cluster health check. `SlurmAdapter` requires a separately supplied transport. No implicit connection/automatic activation occurs.

## Future administrator setup, not performed in this delivery

1. Independently provision/review an SSH alias and verified known-host entry on the backend host. No credentials are requested by this app. Transport uses system `/usr/bin/ssh`, BatchMode, strict host-key checks and a10s connection timeout; no interactive prompts or automatic trust installation. Using it later will make SSH read that administrator-managed configuration.
2. Fill `.private/slurm.json` locally; leave `enabled:false` until ready for separately authorized integration testing. Alias permits a simple name, not an option/command. Remote root and xTB executable require absolute paths without spaces, `..`, symlink components or shell metacharacters. Root must already exist remotely, owned by the SSH user and private0700. All path components are opened with O_NOFOLLOW. Python3, Bash, sbatch, sacct and scancel must be available on that login host. Accounting must expose JobIDRaw, JobName, State, ExitCode and WorkDir. Federated/array/heterogeneous submissions are deliberately unsupported.
3. Fill CPU1–128, memory128–262144MiB, time1–1440minutes; no guessed cluster allocations. Partition/account may stay blank if cluster defaults are valid. Fill the absolute xTB executable and explicit environment setup (modules/activation as appropriate for the site). The parser only accepts verified xTB6.6.1. `site_preamble` is an optional administrator-reviewed site prologue, not an arbitrary replacement submission command. Template uses `--export=NIL`; verify local Slurm support before use.
4. After separately authorized real integration, an administrator may instantiate the adapter from private maintenance code, never from the public API:

```python
from pathlib import Path
from backend.slurm import Config, SlurmAdapter, SSHTransport
root = Path('/path/to/molecular-workbench')
cfg = Config.load(root / '.private/slurm.json')
# This returns not connected and does not invoke SSH:
print(SlurmAdapter(cfg, root / '.private/slurm-receipts').connection())
# Only a fully configured/enabled admin configuration can construct transport.
# Do not execute this against a real host without separate integration approval:
# adapter = SlurmAdapter(cfg, root / '.private/slurm-receipts', SSHTransport(cfg))
```

An adapter call `submit({'xyz': ..., 'charge':0, 'uhf':0, 'mode':'sp' or 'opt'})` accepts only these fixed molecular fields, validates geometry/electron parity, stages immutable raw/normalized input and a generated script, and records a receipt before issuing sbatch. Receipts are independent of the local job database. Each submission uses a UUID directory and unique `wb_<uuid>` scheduler name; no existing directory is reused. Resource limits/parameters and hashes are retained. Transport uses an argument array locally and shell-quotes every remote argv item, limits total output21MiB/time30s, and kills only its own SSH process group on failure.

`sbatch --parsable` must return one numeric ID; a timeout, warning-contaminated reply or cluster-qualified ID leaves `submission_unknown` persisted. **Never automatically retry such a submission.** Reconcile manually on the actual cluster by receipt's unique name/workdir/user, then build a separately reviewed recovery mechanism. This scaffold has no automatic reconciliation/resubmission and no scheduler polling loop. Call operations serially from one admin process; concurrent receipt mutation is not supported.

`status` uses sacct allocation rows and verifies exact job ID, UUID name and workdir. Missing accounting data is UNKNOWN, never success or permission to cancel/read. `cancel` verifies identity first and sends scancel with job ID + exact name + `--me --ctld`; it records cancellation requested, not cancellation completed. Re-query later. Stale/mismatched identity cannot cancel unrelated jobs. Scheduler COMPLETED or exit0 alone is not scientific success.

`artifact` only returns output.log (20MiB), engine.version (8KiB), xtbopt.xyz (128KiB); remote helper verifies directory ownership/privacy, marker, normalized-input hash, regular-file type, no symlinks and size limits. Raw optimizer output is an unvalidated artifact. `collect` requires COMPLETED/0:0 and actual xTB6.6.1, reuses the existing SCC/energy/geometry parser, and persists final.xyz only after successful scientific validation. It also stores fetched log/version/optimizer output privately. No public artifact URLs or arbitrary remote paths exist.

## Required real acceptance before any enabling/integration

Not run here: SSH connectivity/host-key/auth checks, site module/environment execution, sbatch/sacct/scancel compatibility or a real remote job.

Before adding any UI/API HPC mode, separately authorize and verify:

- Isolated dedicated root permissions, quotas, ownership, available commands and Slurm version/accounting fields; clean noninteractive SSH output; stdout size/time limits and denied host-key behavior.
- One public-water single point and optimization, compare remote results to direct same-version CLI (energy/convergence/atom sequence); inspect actual CPU, memory, time, environment and exit status on compute nodes. Verify missing executable/version/module/setup errors fail honestly.
- Pending/running/terminal accounting, delayed/expired accounting UNKNOWN, timeout/OOM/preemption/failure, cancellation of owned job only, wrong identity refusal and scheduler ID reuse/name filters.
- SSH loss before/after sbatch, ambiguous output, service/admin-process restart, durable receipt recovery and manual no-duplicate reconciliation. Remote jobs intentionally survive loss of the local SSH caller; no automatic cancellation/resubmission is assumed.
- Retrieval of normal/oversized/symlink/missing/modified artifacts and disk-full errors. Establish remote retention/cleanup policy; this scaffold performs no remote deletion.
- A separately reviewed authenticated authorization boundary, per-user/account access, quotas/queue ownership and admin config management. **The current unauthenticated public deployment must not expose this adapter**, even after configuration is filled.

## Verification scope

Slurm tests use mocked transport and temporary local directories. No real cluster connection or remote job has been verified. Three historical-log replay tests are marked skipped in this source release because recorded runtime data is excluded. Existing local engine tests generate their own benign public-water inputs/results in temporary directories.

Official command semantics: [sbatch](https://slurm.schedmd.com/sbatch.html), [scancel](https://slurm.schedmd.com/scancel.html). Real site/version behavior requires the acceptance tests above.
