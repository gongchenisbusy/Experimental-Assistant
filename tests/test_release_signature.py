from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ea.release_package import write_release_package
from ea.release_signature import (
    generate_release_keypair,
    keygen_main,
    sign_main,
    sign_release_package,
    verify_main,
    verify_release_signature,
)
from test_release_manifest import _minimal_release_root


def _key_paths(tmp_path: Path, name: str = "release") -> tuple[Path, Path]:
    return tmp_path / f"{name}-private.pem", tmp_path / f"{name}-public.pem"


def test_release_signature_keygen_sign_and_verify_pass(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    package = write_release_package(
        root, output=Path("dist/release.zip"), archive_root="ea-release"
    )
    private_key, public_key = _key_paths(tmp_path)

    keygen = generate_release_keypair(
        private_key_path=private_key, public_key_path=public_key
    )
    signed = sign_release_package(
        Path(package["archive_path"]),
        private_key_path=private_key,
        public_key_path=public_key,
        key_id="test-key",
        signed_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    verified = verify_release_signature(
        Path(package["archive_path"]), public_key_path=public_key
    )

    assert keygen["status"] == "complete"
    assert signed["status"] == "complete"
    assert Path(signed["signature_path"]).exists()
    assert verified["status"] == "pass"
    assert verified["package_verification"]["status"] == "pass"

    sidecar = yaml.safe_load(Path(signed["signature_path"]).read_text(encoding="utf-8"))
    assert sidecar["payload"]["signature_type"] == "ea_v0_9_8_release_package_signature"
    assert sidecar["payload"]["algorithm"] == "ed25519"
    assert sidecar["payload"]["public_key"]["key_id"] == "test-key"
    assert sidecar["payload"]["archive"]["filename"] == "release.zip"


def test_release_signature_verifier_reports_tampered_archive(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    package = write_release_package(
        root, output=Path("dist/release.zip"), archive_root="ea-release"
    )
    private_key, public_key = _key_paths(tmp_path)
    generate_release_keypair(private_key_path=private_key, public_key_path=public_key)
    sign_release_package(
        Path(package["archive_path"]),
        private_key_path=private_key,
        public_key_path=public_key,
    )
    Path(package["archive_path"]).write_bytes(
        Path(package["archive_path"]).read_bytes() + b"tampered"
    )

    verified = verify_release_signature(
        Path(package["archive_path"]), public_key_path=public_key
    )

    assert verified["status"] == "fail"
    assert {
        "path": package["archive_path"],
        "reason": "package_verification_failed",
    } in verified["failures"]
    assert any(
        failure["reason"] == "archive_size_mismatch" for failure in verified["failures"]
    )
    assert any(
        failure["reason"] == "archive_sha256_mismatch"
        for failure in verified["failures"]
    )


def test_release_signature_verifier_reports_changed_checksum_sidecar(
    tmp_path: Path,
) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    package = write_release_package(
        root, output=Path("dist/release.zip"), archive_root="ea-release"
    )
    private_key, public_key = _key_paths(tmp_path)
    generate_release_keypair(private_key_path=private_key, public_key_path=public_key)
    sign_release_package(
        Path(package["archive_path"]),
        private_key_path=private_key,
        public_key_path=public_key,
    )
    Path(package["archive_checksum_path"]).write_text(
        Path(package["archive_checksum_path"]).read_text(encoding="utf-8")
        + "# comment\n",
        encoding="utf-8",
    )

    verified = verify_release_signature(
        Path(package["archive_path"]), public_key_path=public_key
    )

    assert verified["status"] == "fail"
    assert any(
        failure["reason"] == "checksum_sidecar_sha256_mismatch"
        for failure in verified["failures"]
    )


def test_release_signature_verifier_reports_wrong_public_key(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    package = write_release_package(
        root, output=Path("dist/release.zip"), archive_root="ea-release"
    )
    private_key, public_key = _key_paths(tmp_path, "release")
    wrong_private_key, wrong_public_key = _key_paths(tmp_path, "wrong")
    generate_release_keypair(private_key_path=private_key, public_key_path=public_key)
    generate_release_keypair(
        private_key_path=wrong_private_key, public_key_path=wrong_public_key
    )
    sign_release_package(
        Path(package["archive_path"]),
        private_key_path=private_key,
        public_key_path=public_key,
    )

    verified = verify_release_signature(
        Path(package["archive_path"]), public_key_path=wrong_public_key
    )

    assert verified["status"] == "fail"
    assert any(
        failure["reason"] == "public_key_fingerprint_mismatch"
        for failure in verified["failures"]
    )
    assert any(
        failure["reason"] == "invalid_signature" for failure in verified["failures"]
    )


def test_release_signature_cli_round_trip(tmp_path: Path, capsys) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    package = write_release_package(
        root, output=Path("dist/release.zip"), archive_root="ea-release"
    )
    private_key, public_key = _key_paths(tmp_path)

    keygen_code = keygen_main(
        ["--private-key", str(private_key), "--public-key", str(public_key)]
    )
    keygen_summary = json.loads(capsys.readouterr().out)
    sign_code = sign_main(
        [
            package["archive_path"],
            "--private-key",
            str(private_key),
            "--public-key",
            str(public_key),
        ]
    )
    sign_summary = json.loads(capsys.readouterr().out)
    verify_code = verify_main(
        [package["archive_path"], "--public-key", str(public_key)]
    )
    verify_summary = json.loads(capsys.readouterr().out)

    assert keygen_code == 0
    assert keygen_summary["status"] == "complete"
    assert sign_code == 0
    assert sign_summary["status"] == "complete"
    assert verify_code == 0
    assert verify_summary["status"] == "pass"


def test_release_signature_keygen_refuses_overwrite_without_flag(
    tmp_path: Path,
) -> None:
    private_key, public_key = _key_paths(tmp_path)
    generate_release_keypair(private_key_path=private_key, public_key_path=public_key)

    result = generate_release_keypair(
        private_key_path=private_key, public_key_path=public_key
    )

    assert result["status"] == "fail"
    assert {failure["reason"] for failure in result["failures"]} == {"path_exists"}
