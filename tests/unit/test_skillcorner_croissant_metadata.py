import json
from pathlib import Path
from typing import cast

from fpdbench.data_sources.skillcorner import load_manifest as load_source_manifest
from fpdbench.data_states.skillcorner import load_manifest as load_data_state_manifest
from fpdbench.eligibility.skillcorner import load_manifest as load_eligibility_manifest

ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = ROOT / "src/fpdbench/data_sources/skillcorner_croissant_rai_draft.json"
SUPPORTED_DATA_TYPES = {
    "sc:Boolean",
    "sc:Float",
    "sc:Integer",
    "sc:StructuredValue",
    "sc:Text",
}
SUPPORTED_RAI_PROPERTIES = {
    "rai:dataBiases",
    "rai:dataCollection",
    "rai:dataCollectionMissingData",
    "rai:dataCollectionRawData",
    "rai:dataCollectionType",
    "rai:dataImputationProtocol",
    "rai:dataLimitations",
    "rai:dataManipulationProtocol",
    "rai:dataPreprocessingProtocol",
    "rai:dataReleaseMaintenancePlan",
    "rai:dataSocialImpact",
    "rai:dataUseCases",
    "rai:personalSensitiveInformation",
}


def _all_fields(record_set: dict[str, object]) -> dict[str, dict[str, object]]:
    fields: dict[str, dict[str, object]] = {}

    def collect(field: dict[str, object]) -> None:
        field_id = cast(str, field["@id"])
        assert field_id not in fields
        fields[field_id] = field
        for subfield in cast(list[dict[str, object]], field.get("subField", [])):
            assert subfield["@type"] == "cr:Field"
            collect(subfield)

    for field in cast(list[dict[str, object]], record_set["field"]):
        assert field["@type"] == "cr:Field"
        collect(field)
    return fields


def test_croissant_jsonld_structure_vocabularies_and_references() -> None:
    metadata = json.loads(METADATA_PATH.read_text())
    context = cast(dict[str, object], metadata["@context"])
    assert metadata["@type"] == "sc:Dataset"
    assert context["@vocab"] == "https://schema.org/"
    assert context["sc"] == "https://schema.org/"
    assert context["cr"] == "http://mlcommons.org/croissant/"
    assert context["rai"] == "http://mlcommons.org/croissant/RAI/"
    assert context["prov"] == "http://www.w3.org/ns/prov#"
    assert context["conformsTo"] == "dct:conformsTo"
    assert {key for key in metadata if key.startswith("rai:")} == SUPPORTED_RAI_PROPERTIES
    assert metadata["conformsTo"] == [
        "http://mlcommons.org/croissant/1.1",
        "http://mlcommons.org/croissant/RAI/1.0",
    ]
    assert metadata["version"] == "0.1.0-draft"
    assert metadata["sdVersion"] == "0.1.0-draft"

    defined_ids = {cast(str, metadata["@id"])}
    for record_set in cast(list[dict[str, object]], metadata["recordSet"]):
        record_set_id = cast(str, record_set["@id"])
        assert record_set["@type"] == "cr:RecordSet"
        assert record_set_id not in defined_ids
        defined_ids.add(record_set_id)
        fields = _all_fields(record_set)
        assert fields
        for field_id, field in fields.items():
            assert field_id.startswith(record_set_id + "/")
            assert field_id not in defined_ids
            defined_ids.add(field_id)
            assert field.get("name")
            assert field.get("description")
            assert field.get("dataType") in SUPPORTED_DATA_TYPES
            if field.get("isArray"):
                assert field.get("arrayShape") == "(-1,)"

        raw_keys = record_set.get("key", [])
        keys = raw_keys if isinstance(raw_keys, list) else [raw_keys]
        for key in cast(list[dict[str, str]], keys):
            assert key["@id"] in fields
        for row in cast(list[dict[str, object]], record_set.get("data", [])):
            assert set(row) <= fields.keys()

    assert len(defined_ids) == 1 + sum(
        1 + len(_all_fields(cast(dict[str, object], item)))
        for item in cast(list[dict[str, object]], metadata["recordSet"])
    )

    provenance = cast(dict[str, object], metadata["prov:wasGeneratedBy"])
    used = cast(list[dict[str, str]], provenance["prov:used"])
    expected_resources = {
        "https://github.com/Litju/football-performance-dynamics-bench/blob/main/src/fpdbench/data_sources/skillcorner_open_data_v1.json",
        "https://github.com/Litju/football-performance-dynamics-bench/blob/main/src/fpdbench/data_states/skillcorner_5hz_v1.json",
    }
    assert {resource["@id"] for resource in used} == expected_resources
    for resource in expected_resources | {
        "https://github.com/Litju/football-performance-dynamics-bench/blob/main/src/fpdbench/eligibility/skillcorner_window_v1.json"
    }:
        relative_path = resource.split("/blob/main/", maxsplit=1)[1]
        assert (ROOT / relative_path).is_file()


def test_metadata_bindings_match_repository_authorities() -> None:
    metadata = json.loads(METADATA_PATH.read_text())
    source = load_source_manifest()
    data_state = load_data_state_manifest()
    eligibility = load_eligibility_manifest()
    record_sets = {
        cast(str, item["@id"]): item
        for item in cast(list[dict[str, object]], metadata["recordSet"])
    }

    source_rows = cast(
        list[dict[str, object]],
        cast(dict[str, object], record_sets["source_population"])["data"],
    )
    source_ids = [cast(int, row["source_population/match_id"]) for row in source_rows]
    assert source_ids == cast(list[int], source["selected_source_matches"])
    assert len(source_ids) == 20

    canonical_fields = _all_fields(cast(dict[str, object], record_sets["canonical_observations"]))
    assert (
        canonical_fields["canonical_observations/data_state_id"]["value"]
        == (data_state["data_state_id"])
    )
    assert (
        canonical_fields["canonical_observations/data_state_hash"]["value"]
        == (data_state["data_state_hash"])
    )
    assert (
        canonical_fields["canonical_observations/source_release_id"]["value"]
        == (source["source_release_id"])
    )
    assert (
        canonical_fields["canonical_observations/source_release_hash"]["value"]
        == (source["source_release_hash"])
    )
    assert (
        cast(list[dict[str, str]], metadata["prov:wasDerivedFrom"])[0]["@id"]
        == (cast(dict[str, object], source["upstream"])["pinned_commit_url"])
    )

    policy_set = cast(dict[str, object], record_sets["eligibility_policy"])
    policy_row = cast(list[dict[str, object]], policy_set["data"])[0]
    scientific_policy = cast(dict[str, object], eligibility["scientific_policy"])
    assert policy_row["eligibility_policy/policy_id"] == eligibility["policy_id"]
    assert policy_row["eligibility_policy/policy_version"] == eligibility["policy_version"]
    assert policy_row["eligibility_policy/policy_hash"] == eligibility["policy_hash"]
    assert policy_row["eligibility_policy/source_release_hash"] == source["source_release_hash"]
    assert policy_row["eligibility_policy/data_state_hash"] == data_state["data_state_hash"]
    assert (
        policy_row["eligibility_policy/exclusion_reason_codes"]
        == (scientific_policy["exclusion_reason_codes"])
    )
    assert policy_row["eligibility_policy/warning_codes"] == scientific_policy["warning_codes"]
    assert (
        policy_row["eligibility_policy/quality_strata"]
        == (cast(dict[str, object], scientific_policy["quality_strata"])["dimensions"])
    )


def test_draft_rights_unknowns_and_no_public_distribution_claims() -> None:
    metadata = json.loads(METADATA_PATH.read_text())
    assert "license" not in metadata
    assert "distribution" not in metadata
    assert "datePublished" not in metadata
    assert "citeAs" not in metadata
    assert "contentUrl" not in json.dumps(metadata)
    assert "CONDITIONAL GO" in metadata["rai:dataLimitations"][1]
    assert any("unknown" in value.lower() for value in metadata["rai:dataBiases"])
    assert any("unknown" in value.lower() for value in metadata["rai:personalSensitiveInformation"])

    rights = (ROOT / "docs/data-rights.md").read_text()
    card = (ROOT / "docs/skillcorner-data-card.md").read_text()
    assert "**CONDITIONAL GO**" in rights
    assert "must not host or redistribute" in rights
    assert "not represented as a dataset license" in card
    assert "No DOI" in card
    assert "not full Croissant 1.1 conformance" in card


def test_metadata_bytes_are_deterministic() -> None:
    metadata = json.loads(METADATA_PATH.read_text())
    assert (
        METADATA_PATH.read_text()
        == json.dumps(
            metadata,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
