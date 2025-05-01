import os
import tempfile
from pathlib import Path

import pytest

from src.data_sovereignty import DataVault, OfflineAIModel, ConsentManager


@pytest.fixture()
def tmp_vault(tmp_path):
    return tmp_path / "vault.txt"


def test_vault_store_retrieve(tmp_vault):
    vault = DataVault(vault_path=tmp_vault, key_path=tmp_vault.parent / "key.key")
    vault.store("foo", "bar")
    assert "foo" in vault.list_entries()
    assert vault.retrieve("foo") == b"bar"


def test_offline_model_predict():
    model = OfflineAIModel(weights=[1.0, -1.0], bias=0.0)
    p = model.predict([1.0, 1.0])
    assert 0.0 <= p <= 1.0


def test_consent_manager(tmp_path, monkeypatch):
    consent_file = tmp_path / "consent.json"
    mgr = ConsentManager(consent_path=consent_file)
    # Simulate non-interactive; set environment to ASSUME_YES
    monkeypatch.setenv("ASSUME_YES", "1")
    assert mgr.request("test_action", "desc") is True
    assert mgr.is_allowed("test_action") is True