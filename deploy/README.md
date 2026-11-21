# CI and hosted deployment

The GitHub workflow runs maintained-source syntax checks and authenticated API regressions on Linux and Windows, plus Chromium journeys for the local demo and a temporary HTTPS-hosted fixture. Browser tests use fixtures and never call paid model providers or place trades. `legacy/` is excluded from maintained checks; its known Phase 3 syntax issue and unintegrated modules remain documented in that archive.

## Local checks

```powershell
python -m pip install -r requirements.txt
npm ci
python -B scripts/check_python.py
python -B -m unittest discover -s tests -p 'test_*.py' -v
npx playwright install chromium
npm run test:browser
```

The default `npm run start` remains the loopback-only demo. Hosted mode is a separate single-operator configuration, not a multi-tenant service. Its signed-in operator can access all configured research and broker account views. Sessions are opaque, expire after one hour, are revoked on logout, and reset when the process restarts. Failed logins share a ten-attempt/15-minute limit in that process. Use one application process/replica. Put it behind an HTTPS reverse proxy with request/connection rate limits and body limits; this Python server is intended for a bounded private deployment, not direct public traffic. Live order execution remains disabled.

## Prepare private settings

Run `python scripts/hosting_secrets.py`. It prompts for an operator email, deployment origin and password, then writes a new private file outside the repository. It does not print credentials. Restrict that file to your OS user (on Windows, check its ACL) and back up the encryption key separately. Do not commit or paste its contents into chat.

See `hosted.env.example` for variable names. `SI_TRADER_PUBLIC_ORIGIN` must be the exact HTTPS scheme, domain and optional port, with no trailing slash. Hosting refuses to start without its account, encryption key and an absolute persistent data directory. Existing Windows DPAPI profiles remain usable locally; they cannot be decrypted on Linux. Re-enter their provider keys on the server. New portable entries use authenticated Fernet encryption and require the same environment key after every restart/deployment. Losing that key loses access to saved provider secrets.

`SI_TRADER_DATA_DIR` defaults model profiles to `<data>/models` and research archives to `<data>/research`. A validated historical bundle is still separately required for historical comparisons; set `SI_TRADER_STRATEGY_BUNDLE` once it exists. Back up the volume and keep the encryption key in a separate secret store. Do not share production volumes or credentials with previews. `SI_TRADER_OLLAMA_URL` selects a private HTTP(S) Ollama origin; absent a reachable Ollama service, use a configured cloud connection.

## Optional Docker deployment

On a Linux Docker host, set `SI_TRADER_ENV_FILE` to the private file and run:

```sh
docker compose -f deploy/compose.yml up --build -d
docker compose -f deploy/compose.yml ps
```

The application port is exposed only on the host loopback address. Configure an HTTPS reverse proxy for the chosen public origin to `http://127.0.0.1:8080`, preserving the public `Host` header. The proxy must not rewrite the browser `Origin`. Keep `/data` persistent and private. Readiness is `GET /healthz`, which reports HTTP service health only, not model/data/broker availability. Check data readiness and model access separately after signing in.

## Self-hosted Stormkit staging

Stormkit is operated separately; its source is not merged into SI-Trader. A server and domain have not yet been supplied. These are the settings to apply once the instance exists:

1. Import `https://github.com/prakashchinnadurai1408/SI-trader`, branch `main`, build root repository root. Use a clean Linux build environment with Python 3.12 selected through `mise.toml`.
2. Build command: `python scripts/build_stormkit.py`. Output folder: `dist`. Start command: `python start_hosted.py`. Use the same Python 3.12 runtime and architecture for build and application execution. This uses Stormkit's **self-hosted Application Runtime**, not Cloud's Node serverless function path.
3. Configure a staging HTTPS domain and set each private variable individually in environment settings. Values from the generated shell environment file are quoted for shell/Compose; remove the outer single quotes when pasting an individual value into Stormkit. `SI_TRADER_MODE=hosted` is mandatory. `PORT` is supplied by the runtime.
4. Provision private persistent storage for this environment. Set `SI_TRADER_DATA_DIR` to its actual absolute path visible to the application process, not blindly to `/data`. Stormkit's documented filesystem volume layout is `<volume-root>/a<app-id>e<env-id>/`; verify the runtime can write there. Treat volumes as private and maintain backups.
5. Configure `/healthz` as the pre-publish HTTP check, preserve public Host/Origin through the proxy, and allow sufficient proxy response time for model research. Prefer background jobs for long-running workloads as the app grows. Do not enable a preview until its distinct public origin, operator credentials, encryption key and private volume are set.
6. Run all GitHub CI checks before deployment. Keep automatic production publishing off. With an authenticated session, verify model save/test/delete, research bundle readiness, paper sizing and broker read-only access. Those provider-backed checks require real server configuration and were not proven by fixture tests.
7. Promote the tested artifact/commit to a separately configured production environment after review. Keep the previous artifact available for rollback and back up data before upgrades. Rolling code back does not roll back data or revoke trades; this app remains paper-only.

Stormkit's Git auto-deploy setting alone does not establish that GitHub checks passed. Use a successful CI-triggered deployment mechanism supported by your instance, or manually deploy only green commits initially. No deployment hook, SSH credential or domain is embedded in this repository, and no server has been provisioned.

Official references: [Application Runtime](https://www.stormkit.io/docs/deployments/application-runtime), [self-hosting](https://www.stormkit.io/docs/self-hosting/getting-started), [volumes](https://www.stormkit.io/docs/features/volumes).

## Protect main

Require pull requests, the `CI checks (ubuntu-latest)`, `CI checks (windows-latest)`, `Browser journey` and `Deployment packaging` checks, an up-to-date branch and resolved review conversations. Block branch deletion and force pushes. The owner may merge their own PR once checks pass; one-person repositories need not require a separate approving reviewer. The settings should apply to administrators as well. Preserve existing protection settings when changing them. Review the actual GitHub settings after applying them; a workflow file alone does not protect a branch.
