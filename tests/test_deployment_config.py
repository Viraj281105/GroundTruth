"""The Docker deployment must be able to run the workflow the product documents.

Found in the user audit (Docker stack, real browser): a project created in the web app could
not get satellite observations. Two independent causes, both invisible to the unit tests:

* the API and the worker are separate containers with separate filesystems, so the worker
  could not read the boundary the API had stored ("The project's boundary could not be read"),
  and the API could never have read the observations the worker stored;
* the backend image did not install the satellite ingestion libraries, so the worker would
  have failed on its first import even with the files in place.

These tests read the deployment files as they are written; they start no containers.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
DOCKERFILE = (ROOT / "infrastructure" / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads(
    (ROOT / "packages" / "groundtruth" / "pyproject.toml").read_text(encoding="utf-8")
)

# Container paths written by one service and read by the other (WORKDIR is /app).
SHARED_PATHS = {
    "/app/cases/boundaries/projects",  # API writes an uploaded boundary; the worker reads it
    "/app/data/project_documents",  # API writes uploads; must survive a container rebuild
    "/app/data/processed",  # worker writes ingested observations; the API reads them
}


def _mounts(service: str) -> dict[str, str]:
    """``container path -> volume name`` for a compose service."""
    out: dict[str, str] = {}
    for entry in COMPOSE["services"][service].get("volumes", []):
        source, target = str(entry).split(":")[:2]
        out[target] = source
    return out


def test_api_and_worker_share_every_runtime_written_directory() -> None:
    api, worker = _mounts("api"), _mounts("worker")
    for path in SHARED_PATHS:
        assert path in api, f"the API does not mount {path}"
        assert path in worker, f"the worker does not mount {path}"
        assert api[path] == worker[path], f"{path} is not the same volume in both services"


def test_shared_directories_are_named_volumes_that_outlive_containers() -> None:
    declared = set(COMPOSE.get("volumes", {}))
    for path, volume in _mounts("api").items():
        if path in SHARED_PATHS:
            assert volume in declared, f"{volume} is not a declared named volume"


def test_the_image_creates_the_shared_directories_before_dropping_privileges() -> None:
    """A named volume takes its ownership from the image directory it is mounted on. If the
    directory does not exist in the image, Docker creates it root-owned and the unprivileged
    app user cannot write to it."""
    mkdir = re.search(r"^RUN mkdir -p (.+)$", DOCKERFILE, flags=re.M)
    assert mkdir, "the backend image does not create the runtime directories"
    created = {f"/app/{p}" for p in mkdir.group(1).split()}
    assert created >= SHARED_PATHS
    assert DOCKERFILE.index(mkdir.group(0)) < DOCKERFILE.index("chown -R app /app")
    assert DOCKERFILE.index("chown -R app /app") < DOCKERFILE.index("USER app")


def test_the_backend_image_installs_the_ingestion_libraries() -> None:
    extras = PYPROJECT["project"]["optional-dependencies"]
    ingest = " ".join(extras["ingest"])
    for library in ("pystac-client", "planetary-computer", "rasterio"):
        assert library in ingest, f"{library} is missing from the 'ingest' extra"
    install = re.search(r"pip install \"\./packages/groundtruth\[([^\]]+)\]\"", DOCKERFILE)
    assert install, "the backend image does not install the groundtruth package"
    assert "ingest" in install.group(1).split(","), "the image does not install the ingest extra"
    # rasterio's wheel links the system libexpat, absent from python:*-slim.
    assert "libexpat1" in DOCKERFILE
    # and the build itself fails if the libraries cannot be imported
    assert "import rasterio, pystac_client, planetary_computer" in DOCKERFILE


def test_the_web_image_ships_every_local_module_next_config_imports() -> None:
    """Found rebuilding the stack after merging main: next.config.mjs imports
    ./security-headers.mjs, but the image copied only next.config.mjs, so `next start` exited
    with ERR_MODULE_NOT_FOUND and the web container never served a page."""
    web = ROOT / "apps" / "web"
    config = (web / "next.config.mjs").read_text(encoding="utf-8")
    dockerfile = (ROOT / "infrastructure" / "docker" / "web.Dockerfile").read_text(encoding="utf-8")
    local = re.findall(r"from\s+['\"]\./([^'\"]+)['\"]", config)
    assert local, "expected next.config.mjs to import a local module"
    for module in local:
        assert (web / module).is_file(), module
        assert f"/web/{module}" in dockerfile, f"{module} is not copied into the web image"
