# configs

Environment and runtime configuration that is not secret.

Secrets never live here. They are supplied through the environment; see
`.env.example` and [`docs/engineering/configuration.md`](../docs/engineering/configuration.md).

| File | Purpose | Status |
| --- | --- | --- |
| _(none yet)_ | Per-environment overrides land here when there is more than one environment | Planned |

Today all configuration comes from environment variables read by
`groundtruth.platform.config.Settings`. That is sufficient for one environment
and will stay that way until it is not.
