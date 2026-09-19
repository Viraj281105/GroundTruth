# groundtruth (Python distribution)

The GroundTruth Python package. Three subpackages, split by ownership with a
formal contract between them:

| Subpackage | Owner | Contents |
| --- | --- | --- |
| `groundtruth.contracts` | shared | Versioned boundary: `AnalysisRequest`, `AnalysisResult`, `Evidence`, `Provenance`, units, errors, grounding rules, DataAccess ports |
| `groundtruth.engine` | Viraj | The analytical engine. Pure computation, no I/O. |
| `groundtruth.platform` | Bhumi | API, case management, dataset services, jobs, persistence, reporting |

Install for development from the repository root:

```bash
pip install -e "packages/groundtruth[api,genai,dev]"
```

Shared tooling configuration (ruff, mypy, pytest) lives in the root
`pyproject.toml`. See the repository `README.md`, `ARCHITECTURE.md` and
`docs/decisions/ADR-001-monorepo-structure.md`.
