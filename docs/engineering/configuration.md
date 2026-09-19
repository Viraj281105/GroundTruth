# Configuration

All configuration is environment variables, read through
`groundtruth.platform.config.Settings` (pydantic-settings). No config files are
baked into an image; no secrets live in the repository.

---

## Principles

**One source.** Settings are read in one place and passed down. Nothing reaches
for `os.environ` at point of use.

**Secrets are typed.** Credentials are `SecretStr`. Nothing logs a value.
`groundtruth doctor` reports whether a credential is *present*, never what it
is.

**The engine reads no configuration at all.** Everything it needs arrives in the
`AnalysisRequest`. That is what makes a run replayable — configuration is not
carried with a result, so an engine that read it would not be reproducible.

**Absent credentials are not an error.** Every external provider is optional and
the full pipeline runs offline. But a provider *selected* without its key **is**
an error rather than a silent fallback, because a silent fallback would hide a
deployment mistake.

## Settings

See `.env.example` for the complete list with commentary. Grouped:

| Group | Purpose |
| --- | --- |
| App | Environment, log level, random seed |
| Paths | Data, cases and artifacts directories |
| Earth observation | Earth Engine, Sentinel Hub, Global Forest Watch credentials |
| GenAI | Provider selection, model, base URL, keys, generation parameters |
| Services | Database URL, API host and port, frontend origin |
| Analysis defaults | Minimum donors, minimum pre-periods, fit tolerance |

## Path discovery

Repository-relative paths are found by walking up for a marker directory rather
than counting parents. Counting parents is brittle: it broke silently when the
package moved into `packages/groundtruth/` during the monorepo restructure, and
surfaced as "no cases found" rather than as an import error.

## Analysis defaults

`MIN_DONORS`, `MIN_PRE_PERIODS` and `MAX_PRE_RMSE_RATIO` are the robustness
floors. They can be raised per request. Lowering them to push a result past a
gate is exactly the behaviour the gate chain exists to prevent, and should be
treated as a red flag in review.

## Environments

| Environment | Status |
| --- | --- |
| `development` | Implemented — the default |
| `test` | Implemented — used by the suite |
| `production` | Planned — lands with the deployment |

`configs/` holds non-secret per-environment overrides once there is more than
one environment. Today there is not, and an empty directory with a README is
more honest than speculative files that would rot.

## Adding a setting

1. Add it to `Settings` with a type and a description.
2. Add it to `.env.example` with a comment saying what it does and whether it is
   used yet.
3. If it is a credential, make it `SecretStr`.
4. If it changes analytical behaviour, ask whether it belongs in
   `AnalysisRequest` instead — the engine must not read configuration.
