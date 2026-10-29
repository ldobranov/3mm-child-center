# Application starter

This skeleton demonstrates one currently checked profile: approved native Python
application, its own SDK-managed SQLite, public compiled Vue UI and human grants.
It contains no personal data, jobs, connectors, devices, scoped SQL or sessions.
It is not a declaration that arbitrary combinations of those features work.

Edit `application.json` for identity and independent module/wheel versions;
`application_contract.py` is the authoritative descriptor source. Add your own
domain to `service/starter_application` with explicit migrations and behavior
tests. Core remains responsible for login, permission grants, native UI consent,
menu filtering and theme delivery. The service rechecks audience and actor;
human permissions must still be checked by the real Core gateways.

`App.vue` uses `@3mm/application-ui/v1`, `UiSurface` and `UiButton` from
`@3mm/ui/v1`. Use the same public fields/forms/tables when needed. Use `--ui-*`
tokens. Do not import private stores, pass tokens, make direct HTTP calls or
create another theme/language preference store.

The current Core loader supplies the reactive `locale` prop from its effective language.
English is mandatory and used per key when a requested language/key is absent;
Bulgarian is optional reference data, not the fallback. Register further language
JSON catalogues in the application registry. The public host.presentation v1
facade also exposes synchronous initial locale and subscribe/unsubscribe for
consumers outside the route-prop boundary. There is no local language selector.
These APIs require the updated Core; installed initial/live language acceptance
remains in `app-development.json`, separate from local prop/translation tests.

From a Linux/WSL Python environment containing the current Core test dependencies:

```sh
PYTHONDONTWRITEBYTECODE=1 python tools/check_application.py \
  --core-source /path/to/current/3mm \
  --frontend-root /path/to/existing/frontend-toolchain
```

The tool imports current Core source read-only. It builds/stages the exact ZIP,
checks package/preset rules, runs the real separate application host with signed
Unix-socket health and reactivation, behavior tests, strict TypeScript/Vite/UI
tests, and static presentation rules. All retained outputs are in a new
`.runtime/application-checks/<run>/` directory, including `report.json` and logs.
Short Linux temporary socket/data paths are removed after the run. No upload,
installed service, permissions, Core DB or network configuration is changed.

Exit 0 means local automatic checks passed. It does **not** mean release accepted.
`report.json` separately records `release_ready`, manual checks and platform
blockers. Add `--require-ready` for a gate that exits 2 while acceptance is pending.
Windows-only skips, an empty test suite or skipped required tests are not passes.

The migration test and signed request receipt test demonstrate restart/no-replay;
they are not hostile-code isolation, full Core permission/revocation acceptance,
installed ARM/systemd health or a visual review. Keep the manual acceptance list
until real evidence exists. Before adding personal data, add declared export/
erasure and retention policy plus tested workflows; do not copy placeholder
privacy methods that do nothing. Diagnose uncertain effects by original request
identity; never automatically retry with a replacement identity.
