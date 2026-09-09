import pytest

from dep_audit.scan import load_manifest, normalize_entry, scan_dependencies


def test_load_manifest_reads_every_entry():
    deps = load_manifest()
    assert len(deps) == 18
    assert all({"name", "version", "license", "direct"} <= set(d) for d in deps)


def test_scan_without_transitive_keeps_only_direct():
    deps = scan_dependencies(include_transitive=False)
    assert deps
    assert all(dep["direct"] for dep in deps)
    assert len(deps) < len(load_manifest())


def test_normalize_entry_rejects_incomplete_record():
    with pytest.raises(ValueError):
        normalize_entry({"name": "foo", "version": "1.0"})
