"""Tests for the immutable backend release identity bundled by staging CI."""

from app import release


def test_read_release_id_uses_the_ci_stamped_file(tmp_path, monkeypatch) -> None:
    stamped_release = tmp_path / "release_id.txt"
    stamped_release.write_text("commit-sha-run-id\n", encoding="utf-8")
    monkeypatch.setattr(release, "RELEASE_ID_PATH", stamped_release)

    assert release.read_release_id() == "commit-sha-run-id"


def test_read_release_id_falls_back_when_stamp_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(release, "RELEASE_ID_PATH", tmp_path / "missing.txt")

    assert release.read_release_id() == release.DEFAULT_RELEASE_ID
