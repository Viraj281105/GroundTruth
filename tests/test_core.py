"""Tests for the core domain model: units, provenance, evidence and types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from groundtruth.contracts.errors import ProvenanceError
from groundtruth.contracts.evidence import Evidence, EvidenceBuilder, EvidenceBundle
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    Confidence,
    Indicator,
    TimeSeries,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.contracts.units import UnitFamily, assert_not_index_to_carbon, unit_family


class TestUnits:
    def test_known_units_resolve_to_families(self):
        assert unit_family("ndvi") is UnitFamily.INDEX
        assert unit_family("tCO2e") is UnitFamily.CARBON
        assert unit_family("ha") is UnitFamily.AREA

    def test_unknown_unit_is_rejected_not_guessed(self):
        with pytest.raises(ValueError, match="Unknown unit"):
            unit_family("bananas")

    @pytest.mark.parametrize("index", ["ndvi", "evi", "nbr"])
    @pytest.mark.parametrize("carbon", ["tC", "tCO2e"])
    def test_index_to_carbon_conversion_is_forbidden(self, index, carbon):
        """The single most important guard in the system: NDVI is not carbon."""
        with pytest.raises(ValueError, match="is not a carbon stock"):
            assert_not_index_to_carbon(index, carbon)

    def test_index_to_area_conversion_is_allowed(self):
        assert_not_index_to_carbon("ndvi", "ha")

    def test_biomass_to_carbon_is_allowed(self):
        """Biomass to carbon is a legitimate, modelled conversion."""
        assert_not_index_to_carbon("t/ha", "tCO2e")


class TestProvenance:
    def test_computed_provenance_records_code_version(self):
        prov = Provenance.computed(source="s2", method="median", stage="ingestion")
        assert prov.code_version is not None
        assert prov.retrieved_at is not None

    def test_external_provenance_is_marked_third_party(self):
        prov = Provenance.external("Verra registry", "https://example.org")
        assert prov.stage == "external"
        assert prov.method == "published-third-party-figure"

    def test_fingerprint_is_stable_across_retrieval_times(self):
        a = Provenance.computed(source="s2", method="m", stage="causal", parameters={"k": 1})
        b = Provenance.computed(source="s2", method="m", stage="causal", parameters={"k": 1})
        assert a.fingerprint() == b.fingerprint()

    def test_fingerprint_changes_with_parameters(self):
        a = Provenance.computed(source="s2", method="m", stage="causal", parameters={"k": 1})
        b = Provenance.computed(source="s2", method="m", stage="causal", parameters={"k": 2})
        assert a.fingerprint() != b.fingerprint()

    def test_provenance_is_immutable(self):
        prov = Provenance(source="s", method="m")
        with pytest.raises(ValidationError):
            prov.source = "other"


class TestEvidence:
    def test_evidence_requires_provenance(self, provenance):
        item = Evidence(id="a.b", label="x", value=1.0, provenance=provenance)
        assert item.provenance.method == "fixture"

    def test_evidence_rejects_incomplete_provenance(self):
        with pytest.raises((ProvenanceError, ValidationError)):
            Evidence(id="a.b", label="x", value=1.0, provenance=Provenance(source="", method=""))

    def test_evidence_rejects_unknown_unit(self, provenance):
        with pytest.raises(ValidationError):
            Evidence(id="a.b", label="x", value=1.0, unit="furlongs", provenance=provenance)

    def test_evidence_id_must_be_structured(self, provenance):
        with pytest.raises(ValidationError):
            Evidence(id="Not An Id", label="x", value=1.0, provenance=provenance)

    def test_bool_is_not_numeric(self, provenance):
        item = Evidence(id="fit.converged", label="x", value=True, provenance=provenance)
        assert item.is_numeric is False


class TestEvidenceBundle:
    def test_duplicate_ids_are_rejected(self, provenance):
        item = Evidence(id="a.b", label="x", value=1.0, provenance=provenance)
        with pytest.raises(ValidationError):
            EvidenceBundle(case_id="c", items=(item, item))

    def test_require_raises_for_missing_id(self, bundle):
        with pytest.raises(KeyError):
            bundle.require("does.not.exist")

    def test_numeric_values_excludes_strings_and_bools(self, provenance):
        b = EvidenceBundle(
            case_id="c",
            items=(
                Evidence(id="a.num", label="n", value=1.5, provenance=provenance),
                Evidence(id="a.str", label="s", value="text", provenance=provenance),
                Evidence(id="a.bool", label="b", value=True, provenance=provenance),
            ),
        )
        assert b.numeric_values() == {"a.num": 1.5}

    def test_round_trips_through_json(self, bundle):
        restored = EvidenceBundle.from_json(bundle.to_json())
        assert restored.case_id == bundle.case_id
        assert restored.numeric_values() == bundle.numeric_values()
        assert restored.verdict is not None

    def test_with_items_does_not_mutate_the_original(self, bundle, provenance):
        extended = bundle.with_items(
            Evidence(id="new.item", label="n", value=2.0, provenance=provenance)
        )
        assert len(extended) == len(bundle) + 1
        assert "new.item" not in bundle

    def test_builder_collects_items_and_warnings(self, provenance):
        builder = EvidenceBuilder("case")
        builder.add("a.b", "label", 1.0, provenance=provenance)
        builder.warn("something to check")
        built = builder.build()
        assert len(built) == 1
        assert built.warnings == ("something to check",)


class TestTypes:
    def test_time_series_requires_sorted_unique_periods(self):
        with pytest.raises(ValidationError):
            TimeSeries(
                unit_id="u", indicator=Indicator.NDVI, periods=(2002, 2001), values=(0.1, 0.2)
            )

    def test_time_series_infers_unit_from_indicator(self):
        series = TimeSeries(
            unit_id="u", indicator=Indicator.NDVI, periods=(2001, 2002), values=(0.4, 0.5)
        )
        assert series.unit == "ndvi"

    def test_time_series_window_selects_inclusive_range(self):
        series = TimeSeries(
            unit_id="u",
            indicator=Indicator.NDVI,
            periods=(2001, 2002, 2003),
            values=(0.1, 0.2, 0.3),
        )
        assert list(series.window(2002, 2003)) == pytest.approx([0.2, 0.3])

    def test_confidence_rejects_inverted_bounds(self):
        with pytest.raises(ValidationError):
            Confidence(lower=1.0, upper=0.0)

    def test_verdict_always_carries_standard_caveats(self):
        verdict = VerificationVerdict(
            label=VerdictLabel.DIVERGENT_FROM_CLAIM, rationale="r", caveats=()
        )
        for caveat in STANDARD_CAVEATS:
            assert caveat in verdict.caveats

    def test_verdict_labels_never_assert_fraud(self):
        """No verdict label may read as an accusation."""
        forbidden = {"fraud", "fraudulent", "illegal", "guilty"}
        for label in VerdictLabel:
            assert not (set(label.value.lower().split("_")) & forbidden)
