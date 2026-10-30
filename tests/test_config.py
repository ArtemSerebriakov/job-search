from job_search import config


def test_profile_falls_back_to_example_when_personal_profile_missing(tmp_path, monkeypatch):
    (tmp_path / "profile.example.md").write_text("example profile")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert config.load_profile() == "example profile"
    (tmp_path / "profile.md").write_text("my profile")
    assert config.load_profile() == "my profile"


def test_digest_recipient_comes_from_environment(monkeypatch):
    monkeypatch.setenv("DIGEST_RECIPIENT", "someone@example.com")
    assert config.digest_recipient() == "someone@example.com"
    monkeypatch.delenv("DIGEST_RECIPIENT")
    assert config.digest_recipient() is None


def test_all_config_files_parse_and_browser_entries_are_complete():
    # A YAML quoting mistake in sources.yaml (2026-10-30) would have crashed the whole morning run.
    import json
    from job_search.sources.registry import load_sources_config
    config.load_criteria()
    sources = load_sources_config()
    for entry in sources["browser_careers"]:
        assert entry["company"] and entry["link_pattern"] and entry["urls"]
        assert all(u.startswith("https://") for u in entry["urls"])
    json.loads((config.CONFIG_DIR / "browser-mcp.json").read_text())
