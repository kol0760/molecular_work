# Validation and limits

The `Native Windows and Linux` GitHub Actions workflow runs the full pytest suite
on `windows-latest` and `ubuntu-latest`, plus frontend compilation and model tests.
It fetches official upstream xTB v6.7.1 Linux and v6.7.1pre Windows archives into
runner temporary storage and verifies pinned SHA-256 digests. These engines are
CI dependencies only, never redistributed in this source package.

Tests cover real water single-point/optimization calculations and direct CLI
comparisons, actual nonconvergence, unknown-version acceptance, nonzero exit
rejection, missing engines, queue limits, cancellation, restart recovery,
SQLite persistence, API protections, logs/downloads, locks and owned process
cleanup. Startup is exercised over real loopback HTTP from a temporary project
path containing spaces and Unicode. The Windows CMD diagnostic entry is also
executed natively. Three historical recorded-log replay tests remain skipped
because private runtime evidence is intentionally excluded; fresh CLI tests
replace those historical fixtures.

Windows process containment uses kill-on-close Job Objects and a parent process
handle watcher, not Linux emulation. Windows 10/11 nested jobs are required;
containment errors fail before engine launch. CI is a hosted Windows machine,
not validation of any user's physical PC. No physical user computer, real Slurm
cluster, SSH credentials or production service is used. Slurm remains a disabled
administrator scaffold, outside the web API.

Linux uses RLIMIT CPU/address space/file size. Windows uses Job Object CPU and
aggregate committed-memory limits, and application polling for wall time and
log size. Windows does not provide identical Linux file-size enforcement;
a fast writer can briefly exceed the log threshold before termination.

Unknown xTB versions may change output formats: no version is refused, but
unrecognized convergence/energy/geometry output is conservatively rejected.
Version banners are provenance, not proof of scientific correctness. These checks
do not establish physical accuracy or a global minimum.

The source audit scans the explicit release manifest, including built frontend,
for forbidden runtime/private files and common credential formats. It is not a
proof that every possible secret format can be recognized.
