from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ea import __version__
from ea.release_package import (
    _checksum_sidecar_path,
    _sha256_file,
    verify_release_package,
)


SIGNATURE_SIDECAR_SUFFIX = ".sig.yml"
SIGNATURE_TYPE = "ea_v0_9_9_release_package_signature"
LEGACY_SIGNATURE_TYPES = {
    "ea_v0_9_8_release_package_signature",
    "ea_v0_9_7_release_package_signature",
}
SIGNATURE_ALGORITHM = "ed25519"


def _signature_sidecar_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}{SIGNATURE_SIDECAR_SUFFIX}")


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    digest = hashes.Hash(hashes.SHA256())
    digest.update(data)
    return digest.finalize().hex()


def _load_passphrase(env_name: str | None) -> bytes | None:
    if not env_name:
        return None
    value = os.environ.get(env_name)
    return value.encode("utf-8") if value else None


def _load_private_key(
    path: Path, *, passphrase: bytes | None = None
) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private_key_not_ed25519")
    return key


def _load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("public_key_not_ed25519")
    return key


def _public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _sha256_bytes(public_bytes)


def _private_key_public_fingerprint(private_key: Ed25519PrivateKey) -> str:
    return _public_key_fingerprint(private_key.public_key())


def _public_key_record(
    public_key_path: Path, *, key_id: str | None = None
) -> dict[str, Any]:
    public_key = _load_public_key(public_key_path)
    return {
        "key_id": key_id,
        "path_hint": public_key_path.name,
        "fingerprint_sha256": _public_key_fingerprint(public_key),
    }


def generate_release_keypair(
    *,
    private_key_path: Path,
    public_key_path: Path,
    overwrite: bool = False,
    passphrase: bytes | None = None,
) -> dict[str, Any]:
    private_key_path = private_key_path.resolve()
    public_key_path = public_key_path.resolve()
    existing = [path for path in [private_key_path, public_key_path] if path.exists()]
    if existing and not overwrite:
        return {
            "schema_version": "0.9",
            "operation": "release_keygen",
            "status": "fail",
            "failures": [
                {"path": str(path), "reason": "path_exists"} for path in existing
            ],
        }

    private_key = Ed25519PrivateKey.generate()
    encryption: serialization.KeySerializationEncryption
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_bytes(private_bytes)
    public_key_path.write_bytes(public_bytes)
    try:
        private_key_path.chmod(0o600)
        public_key_path.chmod(0o644)
    except OSError:
        pass

    return {
        "schema_version": "0.9",
        "operation": "release_keygen",
        "status": "complete",
        "algorithm": SIGNATURE_ALGORITHM,
        "private_key_path": str(private_key_path),
        "public_key_path": str(public_key_path),
        "private_key_encrypted": bool(passphrase),
        "public_key_fingerprint_sha256": _private_key_public_fingerprint(private_key),
        "user_managed_key_required": True,
    }


def sign_release_package(
    archive_path: Path,
    *,
    private_key_path: Path,
    public_key_path: Path,
    signature_path: Path | None = None,
    checksum_path: Path | None = None,
    key_id: str | None = None,
    passphrase: bytes | None = None,
    signed_at: datetime | None = None,
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    private_key_path = private_key_path.resolve()
    public_key_path = public_key_path.resolve()
    signature_path = (signature_path or _signature_sidecar_path(archive_path)).resolve()
    checksum_path = (checksum_path or _checksum_sidecar_path(archive_path)).resolve()

    failures: list[dict[str, Any]] = []
    if not archive_path.exists():
        failures.append({"path": str(archive_path), "reason": "missing_archive"})
    if not private_key_path.exists():
        failures.append(
            {"path": str(private_key_path), "reason": "missing_private_key"}
        )
    if not public_key_path.exists():
        failures.append({"path": str(public_key_path), "reason": "missing_public_key"})
    if failures:
        return {
            "schema_version": "0.9",
            "operation": "release_package_sign",
            "status": "fail",
            "failures": failures,
        }

    try:
        private_key = _load_private_key(private_key_path, passphrase=passphrase)
        public_record = _public_key_record(public_key_path, key_id=key_id)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "schema_version": "0.9",
            "operation": "release_package_sign",
            "status": "fail",
            "failures": [
                {
                    "path": str(private_key_path),
                    "reason": "invalid_signing_key",
                    "detail": str(exc),
                }
            ],
        }
    private_fingerprint = _private_key_public_fingerprint(private_key)
    if private_fingerprint != public_record["fingerprint_sha256"]:
        return {
            "schema_version": "0.9",
            "operation": "release_package_sign",
            "status": "fail",
            "failures": [
                {
                    "path": str(public_key_path),
                    "reason": "public_key_does_not_match_private_key",
                    "private_key_public_fingerprint_sha256": private_fingerprint,
                    "public_key_fingerprint_sha256": public_record[
                        "fingerprint_sha256"
                    ],
                }
            ],
        }

    checksum_record = None
    if checksum_path.exists():
        checksum_record = {
            "filename": checksum_path.name,
            "sha256": _sha256_file(checksum_path),
        }
    payload = {
        "schema_version": "0.9",
        "signature_type": SIGNATURE_TYPE,
        "algorithm": SIGNATURE_ALGORITHM,
        "archive": {
            "filename": archive_path.name,
            "size_bytes": archive_path.stat().st_size,
            "sha256": _sha256_file(archive_path),
        },
        "checksum_sidecar": checksum_record,
        "public_key": public_record,
        "signed_at_utc": (signed_at or datetime.now(UTC))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "user_managed_key_required": True,
    }
    payload_bytes = _canonical_payload_bytes(payload)
    signature_value = base64.b64encode(private_key.sign(payload_bytes)).decode("ascii")
    sidecar = {
        "payload": payload,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "encoding": "base64",
            "signed_payload_sha256": _sha256_bytes(payload_bytes),
            "value": signature_value,
        },
    }
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    return {
        "schema_version": "0.9",
        "operation": "release_package_sign",
        "status": "complete",
        "archive_path": str(archive_path),
        "signature_path": str(signature_path),
        "public_key_path": str(public_key_path),
        "public_key_fingerprint_sha256": public_record["fingerprint_sha256"],
        "signed_payload_sha256": sidecar["signature"]["signed_payload_sha256"],
        "archive_sha256": payload["archive"]["sha256"],
    }


def verify_release_signature(
    archive_path: Path,
    *,
    public_key_path: Path,
    signature_path: Path | None = None,
    checksum_path: Path | None = None,
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    public_key_path = public_key_path.resolve()
    signature_path = (signature_path or _signature_sidecar_path(archive_path)).resolve()
    checksum_path = (checksum_path or _checksum_sidecar_path(archive_path)).resolve()
    result: dict[str, Any] = {
        "schema_version": "0.9",
        "check_type": "ea_v0_9_8_release_package_signature",
        "status": "pass",
        "archive_path": str(archive_path),
        "signature_path": str(signature_path),
        "public_key_path": str(public_key_path),
        "algorithm": SIGNATURE_ALGORITHM,
        "package_verification": None,
        "failures": [],
    }

    package_verification = verify_release_package(
        archive_path, checksum_path=checksum_path
    )
    result["package_verification"] = package_verification
    if package_verification["status"] != "pass":
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(archive_path), "reason": "package_verification_failed"}
        )
    if not signature_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(signature_path), "reason": "missing_signature_sidecar"}
        )
        return result
    if not public_key_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(public_key_path), "reason": "missing_public_key"}
        )
        return result

    try:
        sidecar = yaml.safe_load(signature_path.read_text(encoding="utf-8")) or {}
        payload = sidecar.get("payload") or {}
        signature = sidecar.get("signature") or {}
        payload_bytes = _canonical_payload_bytes(payload)
        signed_payload_sha256 = _sha256_bytes(payload_bytes)
        if signature.get("signed_payload_sha256") != signed_payload_sha256:
            result["status"] = "fail"
            result["failures"].append(
                {
                    "path": str(signature_path),
                    "reason": "signed_payload_sha256_mismatch",
                    "expected_sha256": signature.get("signed_payload_sha256"),
                    "actual_sha256": signed_payload_sha256,
                }
            )
        if payload.get("signature_type") not in {
            SIGNATURE_TYPE,
            *LEGACY_SIGNATURE_TYPES,
        }:
            result["status"] = "fail"
            result["failures"].append(
                {"path": str(signature_path), "reason": "unexpected_signature_type"}
            )
        if (
            payload.get("algorithm") != SIGNATURE_ALGORITHM
            or signature.get("algorithm") != SIGNATURE_ALGORITHM
        ):
            result["status"] = "fail"
            result["failures"].append(
                {
                    "path": str(signature_path),
                    "reason": "unexpected_signature_algorithm",
                }
            )
        archive_record = payload.get("archive") or {}
        if archive_record.get("filename") != archive_path.name:
            result["status"] = "fail"
            result["failures"].append(
                {"path": str(archive_path), "reason": "archive_filename_mismatch"}
            )
        if archive_path.exists():
            actual_size = archive_path.stat().st_size
            actual_sha = _sha256_file(archive_path)
            if archive_record.get("size_bytes") != actual_size:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": str(archive_path),
                        "reason": "archive_size_mismatch",
                        "expected_size_bytes": archive_record.get("size_bytes"),
                        "actual_size_bytes": actual_size,
                    }
                )
            if archive_record.get("sha256") != actual_sha:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": str(archive_path),
                        "reason": "archive_sha256_mismatch",
                        "expected_sha256": archive_record.get("sha256"),
                        "actual_sha256": actual_sha,
                    }
                )
        checksum_record = payload.get("checksum_sidecar")
        if checksum_record:
            if checksum_record.get("filename") != checksum_path.name:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": str(checksum_path),
                        "reason": "checksum_sidecar_filename_mismatch",
                    }
                )
            if not checksum_path.exists():
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": str(checksum_path),
                        "reason": "missing_signed_checksum_sidecar",
                    }
                )
            else:
                actual_checksum_sidecar_sha = _sha256_file(checksum_path)
                if checksum_record.get("sha256") != actual_checksum_sidecar_sha:
                    result["status"] = "fail"
                    result["failures"].append(
                        {
                            "path": str(checksum_path),
                            "reason": "checksum_sidecar_sha256_mismatch",
                            "expected_sha256": checksum_record.get("sha256"),
                            "actual_sha256": actual_checksum_sidecar_sha,
                        }
                    )
        public_key = _load_public_key(public_key_path)
        public_fingerprint = _public_key_fingerprint(public_key)
        sidecar_fingerprint = (payload.get("public_key") or {}).get(
            "fingerprint_sha256"
        )
        result["public_key_fingerprint_sha256"] = public_fingerprint
        if sidecar_fingerprint != public_fingerprint:
            result["status"] = "fail"
            result["failures"].append(
                {
                    "path": str(public_key_path),
                    "reason": "public_key_fingerprint_mismatch",
                    "expected_fingerprint_sha256": sidecar_fingerprint,
                    "actual_fingerprint_sha256": public_fingerprint,
                }
            )
        try:
            public_key.verify(
                base64.b64decode(signature.get("value") or ""), payload_bytes
            )
        except (InvalidSignature, ValueError):
            result["status"] = "fail"
            result["failures"].append(
                {"path": str(signature_path), "reason": "invalid_signature"}
            )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        result["status"] = "fail"
        result["failures"].append(
            {
                "path": str(signature_path),
                "reason": "invalid_signature_sidecar",
                "detail": str(exc),
            }
        )
    return result


def build_keygen_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Generate an Ed25519 keypair for optional Experimental Assistant v{__version__} signing."
    )
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--passphrase-env")
    return parser


def build_sign_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Sign an Experimental Assistant v{__version__} package with a user-managed Ed25519 private key."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--key-id")
    parser.add_argument("--passphrase-env")
    return parser


def build_verify_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Verify an Experimental Assistant v{__version__} package detached signature."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--checksum", type=Path)
    return parser


def keygen_main(argv: list[str] | None = None) -> int:
    args = build_keygen_parser().parse_args(argv)
    result = generate_release_keypair(
        private_key_path=args.private_key,
        public_key_path=args.public_key,
        overwrite=args.overwrite,
        passphrase=_load_passphrase(args.passphrase_env),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


def sign_main(argv: list[str] | None = None) -> int:
    args = build_sign_parser().parse_args(argv)
    result = sign_release_package(
        args.archive,
        private_key_path=args.private_key,
        public_key_path=args.public_key,
        signature_path=args.signature,
        checksum_path=args.checksum,
        key_id=args.key_id,
        passphrase=_load_passphrase(args.passphrase_env),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


def verify_main(argv: list[str] | None = None) -> int:
    args = build_verify_parser().parse_args(argv)
    result = verify_release_signature(
        args.archive,
        public_key_path=args.public_key,
        signature_path=args.signature,
        checksum_path=args.checksum,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(sign_main(sys.argv[1:]))
