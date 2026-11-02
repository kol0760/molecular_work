# Release validation

Verified on Linux x86_64 with Python3.10:

- First setup downloaded/installed all pinned Python packages from public PyPI into an isolated project virtual environment.
-61 Python tests passed;3 historical-log replay tests deliberately skipped (recorded runtime logs are not shipped). One existing Starlette/httpx deprecation warning remains.
-5 geometry/editor model tests passed.
- Actual start-linux.sh launched isolated loopback server on an alternate local port; Chromium imported public water, ran real installed xTB6.6.1 optimization, inspected validated final geometry, downloaded XYZ, refreshed in a mobile viewport, with zero page errors. Test-created state/logs are excluded from distribution.
- Windows launcher received static checks and native-Windows backend rejection tests. **No real Windows or WSL2 machine was tested.** Windows support means the documented WSL2 route, not native Python/EXE.
- No real SSH/Slurm connection or remote submission. Slurm is disabled, not registered in public APIs. No third-party runtime executable is bundled.
- Sanitized source is exported with an explicit file manifest and secret/private-path scan. No old Git history is imported. This is a useful guard, not a guarantee that generic secret scanning catches every possible secret.

The optional GitHub workflow runs Linux offline/mock/API checks and frontend build/model tests. It does not claim real engine, cluster or Windows integration coverage. Workflow execution has not been verified before the repository exists.
