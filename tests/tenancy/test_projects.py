from __future__ import annotations

import codecs
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))
from authhelpers import ORIGIN, new_client, register

from groundtruth.platform.auth.authz import AccessContext
from groundtruth.platform.projects.boundary import BoundaryValidationError, parse_boundary
from groundtruth.platform.projects.service import list_org_projects
from groundtruth.platform.store.models import (
    AuditEventRow,
    OrganizationRow,
    ProjectGrantRow,
    ProjectRow,
)

pytestmark = pytest.mark.usefixtures("_fast_scrypt")
H = {"Origin": ORIGIN}
REPO = Path(__file__).resolve().parents[2]

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30, -1], [30.1, -1], [30.1, -0.9], [30, -0.9], [30, -1]]],
}
BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
POINT = {"type": "Point", "coordinates": [30, -1]}

_KML = (
    '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{}</Document></kml>'
)


def _placemark(x0: float, y0: float) -> str:
    ring = f"{x0},{y0},0 {x0 + 0.1},{y0},0 {x0 + 0.1},{y0 + 0.1},0 {x0},{y0 + 0.1},0 {x0},{y0},0"
    return (
        "<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
        f"{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    )


def _kml(*placemarks: str) -> bytes:
    return _KML.format("".join(placemarks)).encode()


@pytest.fixture(autouse=True)
def _cases_tmp(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cases_dir", tmp_path / "cases")
    return tmp_path / "cases"


def _org(client, name="Demo NGO", type_="ngo"):
    return client.post("/orgs", json={"name": name, "type": type_}, headers=H)


def _fields(**over):
    data = {
        "name": "Riverbank Restoration",
        "country": "Zambia",
        "ecosystem": "miombo",
        "intervention": "reforestation",
        "treatment_start_year": "2018",
    }
    data.update(over)
    return data


def _post(client, slug, boundary, **over):
    files = {"boundary": boundary} if boundary else None
    return client.post(f"/orgs/{slug}/projects", data=_fields(**over), files=files, headers=H)


def _geo(obj):
    return ("b.geojson", json.dumps(obj).encode())


def _project_files(cases_dir: Path) -> list[Path]:
    d = cases_dir / "boundaries" / "projects"
    return list(d.glob("*")) if d.exists() else []


def test_create_project_happy_path(client, sessions, _cases_tmp):
    register(client, "a@example.org")
    _org(client)
    r = _post(client, "demo-ngo", _geo(SQUARE))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "riverbank-restoration" and body["access_level"] == "owner"
    assert body["data_mode"] == "observed"
    with pytest.raises(ValueError):
        uuid.UUID(body["slug"])
    files = _project_files(_cases_tmp)
    assert [f.name for f in files] == [f"{body['id']}.geojson"]
    assert hashlib.sha256(files[0].read_bytes()).hexdigest() == body["boundary_sha256"]
    with sessions() as db:
        n = db.execute(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.action == "project.create")
        ).scalar_one()
        assert n == 1
    assert client.get(f"/projects/{body['id']}").status_code == 200
    assert client.get("/projects/riverbank-restoration").status_code == 200


def test_wrong_org_slug_is_404(client):
    register(client, "a@example.org")
    _org(client)
    assert _post(client, "someone-else", _geo(SQUARE)).status_code == 404


@pytest.mark.parametrize(
    "boundary",
    [
        ("b.geojson", b"{not json"),
        ("b.geojson", json.dumps(POINT).encode()),
        ("b.geojson", json.dumps(BOWTIE).encode()),
        ("b.geojson", b" " * (6 * 1024 * 1024)),
        ("b.kml", _kml()),
    ],
    ids=["invalid-json", "point", "bowtie", "6mb", "empty-kml"],
)
def test_create_project_rejects_bad_boundaries(client, sessions, _cases_tmp, boundary):
    register(client, "a@example.org")
    _org(client)
    r = _post(client, "demo-ngo", boundary)
    assert r.status_code == 422, r.text
    with sessions() as db:
        assert db.execute(select(func.count()).select_from(ProjectRow)).scalar_one() == 0
    assert _project_files(_cases_tmp) == []


def test_create_requires_boundary_file(client):
    register(client, "a@example.org")
    _org(client)
    assert _post(client, "demo-ngo", None).status_code == 422


def test_kml_multi_placemark_is_unioned():
    one = parse_boundary(_kml(_placemark(30, -1)), "a.kml")
    two = parse_boundary(_kml(_placemark(30, -1), _placemark(31, -1)), "a.kml")
    assert two.area_ha == pytest.approx(2 * one.area_ha, rel=1e-6)
    assert two.geojson["features"][0]["geometry"]["type"] == "MultiPolygon"


def test_kml_with_doctype_is_rejected():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><kml/>'
    with pytest.raises(BoundaryValidationError):
        parse_boundary(evil, "a.kml")


_KML_OK = _kml(_placemark(30, -1))


@pytest.mark.parametrize(
    "data",
    [
        codecs.BOM_UTF16_LE + _KML_OK.decode().encode("utf-16-le"),
        b'<?xml version="1.0" encoding="UTF-16"?><kml/>',
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><kml/>'.encode("utf-16"),
        b'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE x [<!ENTITY a "b">]><kml/>',
        b'<?xml version="1.0"?><!ENTITY a "b"><kml/>',
    ],
    ids=["utf16-bom", "utf16-decl", "utf16-doctype", "utf8-doctype", "utf8-entity"],
)
def test_kml_non_utf8_or_entities_rejected(data):
    with pytest.raises(BoundaryValidationError):
        parse_boundary(data, "a.kml")


def test_kml_utf8_bom_is_accepted():
    r = parse_boundary(codecs.BOM_UTF8 + _KML_OK, "a.kml")
    assert r.area_ha > 0
    decl = b'<?xml version="1.0" encoding="utf-8"?>' + _KML_OK.split(b"?>", 1)[1]
    assert parse_boundary(decl, "a.kml").area_ha > 0


def test_unknown_extension_is_rejected():
    with pytest.raises(BoundaryValidationError):
        parse_boundary(b"{}", "a.shp")


def test_boundary_sha_and_area():
    data = (REPO / "cases" / "boundaries" / "kariba-redd.geojson").read_bytes()
    result = parse_boundary(data, "kariba-redd.geojson")
    assert len(result.sha256) == 64
    assert result.area_ha == pytest.approx(1_072_638, rel=0.005)
    assert parse_boundary(data, "kariba-redd.geojson").sha256 == result.sha256


def test_list_includes_granted_projects_with_level(client, sessions):
    register(client, "a@example.org")
    _org(client)
    pid = _post(client, "demo-ngo", _geo(SQUARE)).json()["id"]
    other = new_client(client)
    register(other, "b@example.org")
    _org(other, name="Funder Org", type_="funder")
    assert other.get("/orgs/funder-org/projects").json() == []
    assert other.get(f"/projects/{pid}").status_code == 404
    with sessions() as db:
        funder = db.execute(
            select(OrganizationRow).where(OrganizationRow.slug == "funder-org")
        ).scalar_one()
        db.add(
            ProjectGrantRow(
                id=str(uuid.uuid4()),
                project_id=pid,
                grantee_organization_id=funder.id,
                level="audit",
                created_at=datetime.now(UTC),
            )
        )
        db.commit()
    rows = other.get("/orgs/funder-org/projects").json()
    assert [(r["id"], r["access_level"], r["owner_slug"]) for r in rows] == [
        (pid, "audit", "demo-ngo")
    ]
    assert other.get(f"/projects/{pid}").json()["access_level"] == "audit"
    own = client.get("/orgs/demo-ngo/projects").json()
    assert [r["access_level"] for r in own] == ["owner"]


def test_list_org_projects_unknown_org_is_empty(sessions):
    with sessions() as db:
        assert list_org_projects(db, AccessContext("u", "nope", "ngo", "owner")) == []
