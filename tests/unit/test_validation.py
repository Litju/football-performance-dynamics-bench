from pathlib import Path

from fpdbench.validation.artifacts import validate_artifacts
from fpdbench.validation.naming import validate_naming
from fpdbench.validation.repository import validate_repository


def test_naming_policy_checks_python_config_docs_readme_and_paths(tmp_path: Path) -> None:
    tokens = {
        "source": "R7" + "E",
        "readme": "ALI" + "478",
        "config": "H5" + "F3",
        "docs": "RES" + "-326",
        "path": "SC" + "R0",
        "test_path": "RES" + "-384",
        "artifact": "ALI" + "478",
    }
    files = {
        "src/fpdbench/foo.py": f'value = "{tokens["source"]}"\n',
        "README.md": f"Example: {tokens['readme']}\n",
        "benchmark.toml": f'value = "{tokens["config"]}"\n',
        "docs/foo.md": f"Example: {tokens['docs']}\n",
        f"docs/{tokens['path']}/index.md": "safe\n",
        f"tests/test_{tokens['test_path']}.py": "safe\n",
        f"artifacts/{tokens['artifact']}.bin": "safe\n",
    }
    for relative, contents in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    errors = validate_naming(tmp_path)
    assert len(errors) == len(files)
    assert any("foo.py" in error and tokens["source"] in error for error in errors)
    assert any("README.md" in error and tokens["readme"] in error for error in errors)
    assert any("benchmark.toml" in error and tokens["config"] in error for error in errors)
    assert any("docs/foo.md" in error and tokens["docs"] in error for error in errors)
    assert any(tokens["path"] in error for error in errors)
    assert any("test_" + tokens["test_path"] in error for error in errors)
    assert any(tokens["artifact"] + ".bin" in error for error in errors)


def test_naming_policy_catches_each_historical_identifier_family(tmp_path: Path) -> None:
    tokens = (
        "BM" + "123",
        "SB" + "-R0-" + "BM" + "-001",
        "SC" + "-R0-" + "001",
        "R7" + "D",
        "soccer-trainingload-" + "bmcb",
    )
    for index, token in enumerate(tokens):
        root = tmp_path / f"case_{index}"
        root.mkdir()
        (root / "source.py").write_text(f'value = "{token}"\n')
        assert validate_naming(root)


def test_naming_policy_allows_only_structured_historical_alias_values(tmp_path: Path) -> None:
    alias_value = "ALI" + "478"
    alias_source = tmp_path / "src" / "fpdbench" / "provenance_alias.py"
    alias_source.parent.mkdir(parents=True)
    alias_source.write_text(
        f'HistoricalAlias(value="{alias_value}", '
        'canonical_id="workload_performance_state/whole_session_performance_state")\n'
    )
    assert validate_naming(tmp_path) == ()

    alias_source.write_text(
        f'HistoricalAlias(value="{alias_value}", canonical_id="{alias_value}")\n'
    )
    errors = validate_naming(tmp_path)
    assert len(errors) == 1
    assert "outside structured provenance value" in errors[0]


def test_naming_policy_checks_repository_root_name(tmp_path: Path) -> None:
    root = tmp_path / ("ALI" + "478")
    root.mkdir()
    assert any("forbidden canonical path component" in error for error in validate_naming(root))


def test_naming_policy_rejects_obsolete_project_names_in_content(tmp_path: Path) -> None:
    name = "Association Football " + "Performance Modeling"
    (tmp_path / "README.md").write_text(f"# {name}\n")
    assert any("obsolete project identity" in error for error in validate_naming(tmp_path))


def test_artifact_guard_rejects_private_data_secrets_and_large_files(tmp_path: Path) -> None:
    dataset = tmp_path / "challenge" / "truth.npy"
    dataset.parent.mkdir()
    dataset.write_bytes(b"x")
    (tmp_path / "credential.pem").write_text("secret")
    (tmp_path / "large.bin").write_bytes(b"0123456789")
    errors = validate_artifacts(tmp_path, max_file_bytes=8)
    assert any("checkpoint artifact" in error for error in errors)
    assert any("secret-like" in error for error in errors)
    assert any("exceeds 8 bytes" in error for error in errors)
    assert any("private or challenge" in error for error in errors)


def test_artifact_guard_blocks_model_formats_but_allows_generic_bin(tmp_path: Path) -> None:
    blocked = (
        "model.safetensors",
        "model.onnx",
        "weights.h5",
        "weights.hdf5",
        "model.keras",
        "saved_model.pb",
        "weights.bin",
        "checkpoint/state.bin",
    )
    for name in blocked:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    (tmp_path / "metadata.bin").write_bytes(b"x")
    (tmp_path / "generic.pb").write_bytes(b"x")

    errors = validate_artifacts(tmp_path)
    for name in blocked:
        assert any(name in error for error in errors)
    assert not any("metadata.bin" in error for error in errors)
    assert not any("generic.pb" in error for error in errors)


def test_artifact_guard_rejects_skillcorner_data_paths_and_lfs_pointers(tmp_path: Path) -> None:
    restricted = tmp_path / "data" / "derived" / "window.json"
    restricted.parent.mkdir(parents=True)
    restricted.write_text('{"rows": []}')
    pointer = tmp_path / "tracking.jsonl"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:" + "a" * 64 + "\nsize 100\n"
    )
    allowed_bodypose_sample = tmp_path / "data" / "bodypose" / "sample_1925299_phase406.jsonl.gz"
    allowed_bodypose_sample.parent.mkdir(parents=True)
    allowed_bodypose_sample.write_bytes(b"small licensed sample")

    errors = validate_artifacts(tmp_path)
    assert any("data/derived/window.json" in error for error in errors)
    assert any("Git LFS dataset pointer" in error and "tracking.jsonl" in error for error in errors)
    assert not any("sample_1925299_phase406.jsonl.gz" in error for error in errors)


def test_repository_configuration_matches_python_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    assert validate_repository(root) == ()
