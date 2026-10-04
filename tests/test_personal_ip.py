from chuma_ip_factory.personal_ip import PersonalIPEngine

def test_personal_ip_requires_explicit_consent():
    e = PersonalIPEngine()
    try:
        e.create_seed("owner-1", b"photo", consented=False)
        assert False
    except PermissionError:
        pass

def test_personal_ip_seed_and_passport():
    e = PersonalIPEngine()
    seed = e.create_seed("owner-1", b"photo", consented=True)
    ip = e.create_personal_ip("owner-1", "Vasily", "recognition", seed_id=seed.seed_id)
    e.apply_signals(ip.personal_ip_id, recognition=20, audience=30, reputation=5, momentum=10)
    passport = e.public_passport(ip.personal_ip_id)
    assert passport["metrics"]["personal_ip_score"] > 0
    assert passport["commercial_value"] == "NOT_A_FINANCIAL_VALUATION"
    assert passport["provenance_hash"]

def test_boundaries_and_freeze():
    e = PersonalIPEngine()
    seed = e.create_seed("o", b"x", consented=True)
    ip = e.create_personal_ip("o", "Me", seed_id=seed.seed_id)
    e.set_boundaries(ip.personal_ip_id, voice=True, commercial_use=True)
    assert e.public_passport(ip.personal_ip_id)["boundaries"]["voice"] is True
    e.freeze(ip.personal_ip_id)
    try:
        e.apply_signals(ip.personal_ip_id, recognition=10)
        assert False
    except PermissionError:
        pass

def test_verified_signal_is_distinct_but_bounded():
    e = PersonalIPEngine()
    ip = e.create_personal_ip("o", "Me")
    e.apply_signals(ip.personal_ip_id, recognition=10, reputation=10, verified=True)
    assert e.ips[ip.personal_ip_id].recognition == 11.5
    assert e.ips[ip.personal_ip_id].reputation == 61.5

def test_score_is_not_money():
    e = PersonalIPEngine()
    ip = e.create_personal_ip("o", "Me")
    passport = e.public_passport(ip.personal_ip_id)
    assert passport["commercial_value"] == "NOT_A_FINANCIAL_VALUATION"
