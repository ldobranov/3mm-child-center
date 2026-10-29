# Native application starter

Read DEVELOPMENT.md, application.json and app-development.json first.
Use only public `@3mm/application-ui/v1`, `@3mm/ui/v1` and Python SDK APIs.
This is the verified native application-owned SQLite preset, not scoped SQL.
Do not add jobs or other resource declarations without a separately tested profile.
Use explicit forward migrations; never reset data to make a test pass.
Preserve durable actor-bound request IDs and resolve uncertain effects without replay.
No private Core stores, tokens, fetch wrappers, alternate theme or locale selectors.
The current Core loader supplies the reactive root locale prop. Public
host.presentation v1 also exposes initial/live locale. Installed acceptance is
still required; do not present local preview tests as device verification.
Run tools/check_application.py before delivering a ZIP. A test pass is not installed
acceptance; inspect report.json and its manual/platform blockers. Do not remove
blockers to get a green result. No upload, deployment, commit or publication inferred.
