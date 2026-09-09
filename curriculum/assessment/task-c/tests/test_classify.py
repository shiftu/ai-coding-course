from dep_audit.classify import classify_all, needs_manual_review, risk_level


def test_known_licenses_map_to_expected_level():
    assert risk_level("MIT") == "low"
    assert risk_level("MPL-2.0") == "medium"
    assert risk_level("AGPL-3.0") == "high"


def test_unrecognized_license_is_reported_as_unknown():
    assert risk_level("BeiTech-Commercial-1.1") == "unknown"
    assert risk_level("SomeVendor-Proprietary-1.0") == "unknown"


def test_missing_license_needs_manual_review():
    assert needs_manual_review({"name": "foo", "version": "1.0", "license": ""})
    assert needs_manual_review({"name": "bar", "version": "1.0", "license": "LGPL-3.0"})
    assert not needs_manual_review({"name": "baz", "version": "1.0", "license": "MIT"})


def test_classify_all_does_not_touch_input():
    deps = [{"name": "requests", "version": "2.32.3", "license": "Apache-2.0", "direct": True}]
    out = classify_all(deps)
    assert out[0]["risk"] == "low"
    assert "risk" not in deps[0]
