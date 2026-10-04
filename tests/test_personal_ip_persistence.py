import tempfile

import pytest

from chuma_ip_factory.persistent_personal_ip import PersistentPersonalIPEngine


def test_personal_ip_survives_restart_with_owner_scope_and_passport():
    d = tempfile.TemporaryDirectory()
    db = f"{d.name}/personal-ip.sqlite"

    engine = PersistentPersonalIPEngine(db)
    seed = engine.create_seed(
        "owner-a", b"real-photo-bytes", consented=True, authenticity="REAL"
    )
    ip = engine.create_personal_ip(
        "owner-a", "My Public IP", "recognition", seed_id=seed.seed_id
    )
    engine.set_boundaries(ip.personal_ip_id, voice=True, commercial_use=True)
    engine.apply_signals(
        ip.personal_ip_id,
        recognition=12,
        audience=20,
        reputation=5,
        momentum=7,
        verified=True,
    )
    passport_before = engine.public_passport(ip.personal_ip_id)
    engine.close()

    restored = PersistentPersonalIPEngine(db)
    try:
        passport_after = restored.public_passport(ip.personal_ip_id)
        assert passport_after["personal_ip_id"] == ip.personal_ip_id
        assert passport_after["owner_id"] == "owner-a"
        assert passport_after["metrics"] == passport_before["metrics"]
        assert passport_after["boundaries"]["voice"] is True
        assert passport_after["boundaries"]["commercial_use"] is True
        assert passport_after["history_count"] >= 3
        assert passport_after["provenance_hash"] == passport_before["provenance_hash"]
        assert restored.owner_ips("owner-a")[0].personal_ip_id == ip.personal_ip_id
        assert restored.owner_ips("owner-b") == []
    finally:
        restored.close()
        d.cleanup()


def test_owner_scope_rejects_foreign_personal_ip():
    d = tempfile.TemporaryDirectory()
    db = f"{d.name}/personal-ip.sqlite"
    engine = PersistentPersonalIPEngine(db)
    ip = engine.create_personal_ip("owner-a", "Private IP")
    try:
        with pytest.raises(PermissionError, match="owner_forbidden"):
            engine.assert_owner(ip.personal_ip_id, "owner-b")
    finally:
        engine.close()
        d.cleanup()


def test_frozen_ip_remains_frozen_after_restart():
    d = tempfile.TemporaryDirectory()
    db = f"{d.name}/personal-ip.sqlite"
    engine = PersistentPersonalIPEngine(db)
    ip = engine.create_personal_ip("owner-a", "Frozen IP")
    engine.freeze(ip.personal_ip_id)
    engine.close()

    restored = PersistentPersonalIPEngine(db)
    try:
        current = restored.assert_owner(ip.personal_ip_id, "owner-a")
        assert current.frozen is True
        assert current.status == "FROZEN"
        with pytest.raises(PermissionError, match="personal_ip_frozen"):
            restored.apply_signals(ip.personal_ip_id, recognition=5)
    finally:
        restored.close()
        d.cleanup()
