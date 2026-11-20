# Earlier phase-platform source

This directory preserves the source and documentation from the `master` upload at commit `cc698c697712ff7a9791cf25c0325d3e595d9aae`. The `main` merge also retains that commit as a parent, alongside the maintained application history.

The subsequent Phase 2 upload at `5fb9451` is merged into this same source layout. Its 18 updated or added files include budget management, stop/target handling, kill switches, daily checklists, execution pipelines, strategy and data adapters, and optional backtesting adapters. These additions are preserved as prototype source; they have not been connected to the maintained UI or approved for live execution. The conflicting root package locations were resolved into this directory, and the maintained application's configuration imports were retained.

The data-source ecosystem upload at `c1ec847` is also merged here. Its ten source updates cover the parameter configuration, source catalogue, validation, pipeline orchestration, and price, fundamentals, news/sentiment, regulatory, and shareholding adapters. Folder-location conflicts were resolved into this existing prototype tree. These modules are not wired into the maintained application's feeds or UI; their presence does not establish live coverage of all 48 parameters. Syntax checks passed for the ten incoming files; provider access and end-to-end collection remain unverified.

The runnable application is at the repository root under `nifty100_weekly/`. Launch it with `npm run start` from the repository root. This archive is not loaded by that application and is not an additional deployment.

## Integration decisions

Where the two uploads overlap, the maintained application wins: its current weekly and monthly research, historical-data checks, model connections, evidence handling, broker account views, and recent UI fixes remain in place. The older root-level package was relocated here to prevent competing import paths and duplicate frontends.

Legacy-only modules include the CLI menu, simulation experiments, broker abstractions, admin features, community, tutorials, pricing, and referral modules. Their source is retained here for selective migration, rather than being presented as working features of the current UI.

The original `nifty100_adapter/backtest/phase3_backtester.py` has an unclosed list expression at line 194. This pre-existing syntax error is preserved in the archive; that module is not runnable and is not part of the maintained application's checks. The other archived Python files passed a syntax scan during consolidation. This does not verify their behavior or compatibility.

The legacy HDFC adapter sets a placeholder connection flag and constructs order responses locally. Its outputs do not establish a real broker connection or execution. The enhanced backtester can generate synthetic liquidity and prices. Those paths have not been enabled in the current application or used as evidence of real performance. Legacy authentication is demo code and has not replaced the current local sign-in flow.

Migration of an individual module requires checking its imports against the current interfaces, replacing synthetic or placeholder behavior where applicable, and exercising the resulting user journey. Strategy changes also follow the repository's Arena review and existing data, comparison, and execution gates. The current historical bundle and LLM setup requirements still apply.

Compiled Python caches, saved credentials, user state, admin state, and session data from the old upload were excluded from this working tree. Their presence in existing Git history is unchanged by this consolidation.
