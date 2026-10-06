from pathlib import Path

from fpdbench.validation.artifacts import validate_artifacts
from fpdbench.validation.naming import validate_naming
from fpdbench.validation.repository import validate_repository


def test_naming_policy_positive_and_negative_controls(tmp_path: Path) -> None:
    good_root = tmp_path / "good"
    good_root.mkdir()
    (good_root / "absolute_position_prediction.py").write_text("pass\n")
    assert validate_naming(good_root) == ()

    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    forbidden_components = (
        "ALI123.py",
        "BM123",
        "SBR0",
        "SCR0",
        "H5F3",
        "R7D",
        "R7E",
        "RES-384",
        "soccer-trainingload-bmcb",
    )
    for component in forbidden_components:
        (bad_root / component).mkdir()
    errors = validate_naming(bad_root)
    assert len(errors) == len(forbidden_components)
    assert all(any(component in error for error in errors) for component in forbidden_components)


def test_naming_policy_rejects_obsolete_project_names_in_source(tmp_path: Path) -> None:
    package = tmp_path / "src" / "fpdbench"
    package.mkdir(parents=True)
    (package / "research.py").write_text("name = 'Association Football Performance Modeling'\n")
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


def test_repository_configuration_matches_python_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    assert validate_repository(root) == ()
