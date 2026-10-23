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
