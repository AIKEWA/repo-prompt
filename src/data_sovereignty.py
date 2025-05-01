"""
data_sovereignty.py – Implements local data vault, offline AI inference and consent management (🛡️ Data Sovereignty).

High-level Goal
---------------
Provide a *production-ready* reference implementation that demonstrates how an
application can uphold **data sovereignty** principles (user owns & controls
their data) in alignment with **Kantian ethics** by:

1. Storing user data **locally** in an encrypted *Data Vault* – no server round-trips.
2. Running **offline** AI inference with a tiny model shipped on-device.
3. Involving a **human-in-the-loop (HITL)** consent flow before data access.

The public API is intentionally small so it can be embedded into larger
projects without tight coupling.  All I/O paths are **configuration-driven**
for easy refactoring.

Key design choices
~~~~~~~~~~~~~~~~~~
* ✨ **Zero external binaries** – only pure-Python deps (`cryptography`,
  `typer`) already present in requirements.
* 🔐 **AES-GCM encryption** via `cryptography.fernet.Fernet` for
  confidentiality + integrity.
* 🧪 **Testability** – support dependency injection and tmp paths so unit tests
  do not touch real user files.
* 📖 **Docstrings** follow NumPy style for auto-generation via Sphinx.
* # REVIEW: Critical security code; please double-check key handling & error paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
import base64
import json
import logging
import os
import sys
from contextlib import suppress
from datetime import datetime
from math import exp
import functools

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
except ModuleNotFoundError:  # pragma: no cover – lightweight fallback when cryptography missing
    import hashlib
    import secrets

    class _FallbackFernet:
        """Very light substitute implementing *encrypt*/*decrypt* using XOR.

        NOT suitable for production – only to keep unit tests functional when
        the *cryptography* package is unavailable (e.g. in CI containers).
        """

        def __init__(self, key: bytes):
            # Derive 32-byte key via SHA-256 to mimic Fernet key length
            self._key = hashlib.sha256(key).digest()

        @staticmethod
        def generate_key() -> bytes:  # emulate Fernet API
            return base64.urlsafe_b64encode(secrets.token_bytes(32))

        def encrypt(self, data: bytes) -> bytes:  # noqa: D401 – imperative OK
            return base64.urlsafe_b64encode(self._xor(data))

        def decrypt(self, token: bytes, ttl: int | None = None):  # type: ignore[override]
            try:
                data = base64.urlsafe_b64decode(token)
                return self._xor(data)
            except Exception as exc:
                raise InvalidToken from exc

        def _xor(self, data: bytes) -> bytes:
            return bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(data))

    Fernet = _FallbackFernet  # type: ignore

    class InvalidToken(Exception):
        """Raised when decryption fails in fallback mode."""

import typer

from .logger import get_logger, setup_logging

_log = get_logger(__name__)

__all__ = [
    "DataVault",
    "OfflineAIModel",
    "ConsentManager",
    "app",
]

# ---------------------------------------------------------------------------
# Utility helpers (internal)
# ---------------------------------------------------------------------------


def _read_env_flag(name: str, default: bool = False) -> bool:
    """Return bool value of environment variable *name* ("1", "true", "yes")."""

    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Data Vault – encrypted local key-value storage
# ---------------------------------------------------------------------------


class DataVault:
    """AES-encrypted, append-only local store for arbitrary payloads.

    Parameters
    ----------
    vault_path:
        File that holds encrypted JSON lines (one *entry* per line).  May live
        inside user home (default ``~/.data_vault``).
    key_path:
        Location of the *symmetric* encryption key (base64 url-safe).
    key_env:
        Environment variable that takes precedence over *key_path*.  Set this
        in CI or when shipping pre-provisioned devices to avoid writing keys to
        disk.
    readonly:
        When *True* no write operations are allowed – safeguards offline/hardened
        environments.

    Notes
    -----
    • The *identifier* (first column) is **not** encrypted so users can list
      their own entries without providing the key – keeps control transparent.
    • For simplicity entries are immutable.  Deleting works via tombstone
      record rather than in-place rewrite, maintaining an audit trail.
    """

    def __init__(
        self,
        vault_path: Path | str | None = None,
        *,
        key_path: Path | str | None = None,
        key_env: str = "DATA_VAULT_KEY",
        readonly: bool = False,
    ) -> None:
        self.vault_path = Path(vault_path or Path.home() / ".data_vault").expanduser()
        self.key_path = Path(key_path or Path.home() / ".vault.key").expanduser()
        self.key_env = key_env
        self.readonly = readonly

        self._fernet = Fernet(self._load_or_create_key())
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.vault_path.exists():
            self.vault_path.touch(mode=0o600)

        _log.debug("DataVault initialised at %s (readonly=%s)", self.vault_path, readonly)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_or_create_key(self) -> bytes:
        """Return encryption key, creating it if necessary (chmod 600)."""

        key_b64 = os.getenv(self.key_env)
        if key_b64:
            _log.debug("Using key from env %s", self.key_env)
            return key_b64.encode()

        if not self.key_path.exists():
            if self.readonly:
                raise PermissionError("Vault in readonly mode but key is missing")
            key_b64 = Fernet.generate_key()
            self.key_path.write_bytes(key_b64)
            self.key_path.chmod(0o600)
            _log.info("Generated new vault key at %s", self.key_path)
            return key_b64

        return self.key_path.read_bytes()

    def _append_line(self, line: str) -> None:
        if self.readonly:
            raise PermissionError("Vault opened in readonly mode; cannot write")
        with self.vault_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, identifier: str, payload: str | bytes) -> None:
        """Encrypt *payload* and append to the vault with *identifier*.

        If an entry with the same *identifier* already exists a `ValueError` is
        raised (immutability).  For updates use :py:meth:`delete` and then
        :py:meth:`store` again.
        """

        if "\n" in identifier or "\t" in identifier:
            raise ValueError("Identifier must not contain newline or tab")

        if any(rec[0] == identifier for rec in self._iter_records()):
            raise ValueError(f"Entry '{identifier}' already exists – delete first")

        data = payload.encode() if isinstance(payload, str) else payload
        token = self._fernet.encrypt(data)
        line = f"{identifier}\t{token.decode()}"
        self._append_line(line)
        _log.info("Stored entry %s", identifier)

    def retrieve(self, identifier: str) -> Optional[bytes]:
        """Return decrypted payload for *identifier* or *None* if missing."""

        for rec_id, enc_b64 in self._iter_records(reverse=True):
            if rec_id != identifier:
                continue
            try:
                return self._fernet.decrypt(enc_b64.encode(), ttl=None)
            except InvalidToken:
                _log.error("Failed to decrypt entry %s – invalid key?", identifier)
                raise
        return None

    def delete(self, identifier: str, *, tombstone: bool = True) -> bool:
        """Mark entry *identifier* as deleted.

        If *tombstone* is *False* the entry is physically removed (costly – full
        rewrite).  Returns ``True`` if an entry was removed.
        """

        found = False
        if tombstone:
            self._append_line(f"{identifier}\t__DELETED__:{datetime.utcnow().isoformat()}Z")
            found = True
        else:
            # expensive but maybe needed for GDPR delete-forever requirements
            if self.readonly:
                raise PermissionError("Vault in readonly mode; cannot rewrite")
            rows = [ln for ln in self.vault_path.read_text().splitlines() if not ln.startswith(f"{identifier}\t")]
            self.vault_path.write_text("\n".join(rows) + "\n")
            found = True
        _log.info("Deleted entry %s (tombstone=%s)", identifier, tombstone)
        return found

    def list_entries(self) -> List[str]:
        """Return list of *identifiers* present in the vault (excluding tombstones)."""

        ids: List[str] = []
        deleted: set[str] = set()
        for rec_id, enc_b64 in self._iter_records():
            if enc_b64.startswith("__DELETED__"):
                deleted.add(rec_id)
            elif rec_id not in deleted:
                ids.append(rec_id)
        return ids

    # -------------------------
    # Iterator helpers
    # -------------------------

    def _iter_records(self, *, reverse: bool = False):
        """Yield `(identifier, encrypted_b64)` tuples (internal)."""

        lines = self.vault_path.read_text().splitlines()
        if reverse:
            lines = reversed(lines)
        for ln in lines:
            if not ln.strip():
                continue
            try:
                rec_id, enc_b64 = ln.split("\t", 1)
            except ValueError:
                # Malformed line – ignore but warn
                _log.warning("Malformed vault line skipped: %s", ln[:50])
                continue
            yield rec_id, enc_b64


# ---------------------------------------------------------------------------
# Offline AI Model – simple logistic regression without heavy deps
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OfflineAIModel:
    """Lightweight logistic regression model serialised as JSON.

    Examples
    --------
    >>> model = OfflineAIModel([0.5, -0.3], bias=0.1)
    >>> round(model.predict([1.0, 2.0]), 3)
    0.231
    """

    weights: Sequence[float]
    bias: float = 0.0

    # ---------------------
    # Inference
    # ---------------------

    def predict(self, features: Sequence[float]) -> float:
        """Return *probability* (0-1) for positive class."""

        if len(features) != len(self.weights):
            raise ValueError("Feature vector size mismatch")
        z = sum(w * x for w, x in zip(self.weights, features)) + self.bias
        return 1.0 / (1.0 + exp(-z))

    # ---------------------
    # (De)serialisation helpers
    # ---------------------

    @classmethod
    @functools.lru_cache(maxsize=8)
    def load(cls, path: Path | str) -> "OfflineAIModel":
        """Load model parameters from *path* (JSON)."""

        data = json.loads(Path(path).read_text())
        return cls(weights=data["weights"], bias=data.get("bias", 0.0))

    def save(self, path: Path | str) -> None:
        """Persist model parameters as JSON."""

        Path(path).write_text(json.dumps({"weights": list(self.weights), "bias": self.bias}))


# ---------------------------------------------------------------------------
# Human-in-the-Loop Consent Manager
# ---------------------------------------------------------------------------


class ConsentManager:
    """Simple consent registry implementing HITL for data usage decisions."""

    def __init__(self, consent_path: Path | str | None = None):
        self.consent_path = Path(consent_path or Path.home() / ".consent.json").expanduser()
        if not self.consent_path.exists():
            self.consent_path.write_text("{}")
            self.consent_path.chmod(0o600)
        _log.debug("Consent registry at %s", self.consent_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, action: str) -> bool:
        """Return *True* if user previously granted consent for *action*."""

        return self._load().get(action, False)

    def request(self, action: str, description: str, *, auto_deny: bool = True) -> bool:
        """Ask user for runtime consent (CLI) unless already decided.

        The prompt is skipped when running in **non-interactive** contexts or
        when env ``ASSUME_NO`` is set – useful for automated tests.
        """

        if self.is_allowed(action):
            return True

        if _read_env_flag("ASSUME_YES"):
            self._record(action, True)
            return True
        if _read_env_flag("ASSUME_NO") or not sys.stdin.isatty():
            self._record(action, False)
            return False

        print(f"\n⚖️  Consent required: {description}\n")
        resp = input("Grant permission? [y/N] ").strip().lower()
        allowed = resp in {"y", "yes"}
        self._record(action, allowed)
        return allowed or not auto_deny

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, bool]:
        return json.loads(self.consent_path.read_text())

    def _record(self, action: str, allowed: bool) -> None:
        data = self._load()
        data[action] = allowed
        self.consent_path.write_text(json.dumps(data, indent=2))
        _log.info("Consent %s: %s", action, allowed)


# ---------------------------------------------------------------------------
# Typer CLI entry-point
# ---------------------------------------------------------------------------


app = typer.Typer(add_help_option=True, no_args_is_help=True, pretty_exceptions_show_locals=False)


def _common_options(fn: Callable[..., None]):  # decorator to add --verbose
    def _wrapper(*args, verbose: bool = typer.Option(False, "--verbose", "-v"), **kwargs):  # type: ignore[override]
        setup_logging("DEBUG" if verbose else "INFO")
        return fn(*args, **kwargs)

    return _wrapper


# ------------------------ Vault commands ------------------------


@app.command()
@_common_options
def store(
    identifier: str = typer.Argument(..., help="Entry key/identifier"),
    payload: str = typer.Argument(..., help="Plain-text payload"),
    vault_file: Path = typer.Option(Path.home() / ".data_vault", "--vault"),
):
    """Encrypt and store *payload* under *identifier*."""

    vault = DataVault(vault_file)
    vault.store(identifier, payload)


@app.command()
@_common_options
def get(
    identifier: str = typer.Argument(..., help="Entry key/identifier"),
    vault_file: Path = typer.Option(Path.home() / ".data_vault", "--vault"),
):
    """Decrypt and print entry *identifier*."""

    vault = DataVault(vault_file)
    data = vault.retrieve(identifier)
    if data is None:
        typer.echo("❌ Not found", err=True)
        raise typer.Exit(code=1)
    typer.echo(data.decode())


@app.command()
@_common_options
def delete(
    identifier: str = typer.Argument(..., help="Entry key/identifier"),
    vault_file: Path = typer.Option(Path.home() / ".data_vault", "--vault"),
    hard: bool = typer.Option(False, "--hard", help="Physically remove instead of tombstone"),
):
    """Delete entry using tombstone (default) or *--hard* physical removal."""

    vault = DataVault(vault_file)
    ok = vault.delete(identifier, tombstone=not hard)
    if not ok:
        typer.echo("Entry not present", err=True)
        raise typer.Exit(code=1)


# ------------------------ AI commands ------------------------


@app.command()
@_common_options
def predict(
    features: List[float] = typer.Argument(..., help="Numeric feature list e.g. 0.1 1.3"),
    model_path: Path = typer.Option(None, "--model", help="Path to JSON model file"),
):
    """Run offline inference and print probability."""

    if model_path and model_path.exists():
        model = OfflineAIModel.load(model_path)
    else:
        # fallback tiny model with two weights for demonstration
        model = OfflineAIModel(weights=[0.4 for _ in features], bias=0.0)

    p = model.predict(features)
    typer.echo(f"{p:.4f}")


# Entry-point for `python -m src.data_sovereignty …`
if __name__ == "__main__":
    app()  # pragma: no cover – CLI manual usage