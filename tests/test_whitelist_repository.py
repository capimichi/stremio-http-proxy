import os
import tempfile
import time

import pytest

from stremio_http_proxy.entity.whitelist_entry import WhitelistEntry
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.repository.whitelist_repository import WhitelistRepository


@pytest.fixture
def repo():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
    tmp.close()
    db_manager = DbManager(tmp.name)
    repository = WhitelistRepository(db_manager)
    yield repository
    os.unlink(tmp.name)


def test_add_and_list_entries(repo: WhitelistRepository):
    e1 = repo.add_entry("a" * 40, "tt1111111")
    e2 = repo.add_entry("b" * 40, "tt1111111", season=1)
    e3 = repo.add_entry("c" * 40, "tt1111111", season=1, episode=2)

    entries = repo.list_entries()
    assert len(entries) == 3

    entries_imdb = repo.list_entries(imdb_id="tt1111111")
    assert len(entries_imdb) == 3


def test_remove_entry(repo: WhitelistRepository):
    e = repo.add_entry("a" * 40, "tt1111111")
    assert repo.remove_entry(e.id) is True
    assert repo.remove_entry(999) is False
    assert len(repo.list_entries()) == 0


def test_get_allowed_infohashes_cumulative(repo: WhitelistRepository):
    repo.add_entry("global", "tt9999999")
    repo.add_entry("season1", "tt9999999", season=1)
    repo.add_entry("s1e2", "tt9999999", season=1, episode=2)

    assert repo.get_allowed_infohashes("tt9999999") == {"global"}
    assert repo.get_allowed_infohashes("tt9999999", season=1) == {"global", "season1"}
    assert repo.get_allowed_infohashes("tt9999999", season=1, episode=2) == {"global", "season1", "s1e2"}
    assert repo.get_allowed_infohashes("tt9999999", season=1, episode=3) == {"global", "season1"}


def test_get_allowed_infohashes_empty_when_no_rules(repo: WhitelistRepository):
    assert repo.get_allowed_infohashes("tt_nonexistent") == set()
    assert repo.get_allowed_infohashes("tt_nonexistent", season=1) == set()


def test_get_allowed_infohashes_separate_imdb(repo: WhitelistRepository):
    repo.add_entry("hash_a", "tt_series_a")
    repo.add_entry("hash_b", "tt_series_b")

    assert repo.get_allowed_infohashes("tt_series_a") == {"hash_a"}
    assert repo.get_allowed_infohashes("tt_series_b") == {"hash_b"}


def test_list_entries_with_filters(repo: WhitelistRepository):
    repo.add_entry("a" * 40, "tt1111111")
    repo.add_entry("b" * 40, "tt2222222", season=2, episode=3)

    by_imdb = repo.list_entries(imdb_id="tt1111111")
    assert len(by_imdb) == 1

    by_imdb2 = repo.list_entries(imdb_id="tt2222222")
    assert len(by_imdb2) == 1
    assert by_imdb2[0].season == 2
    assert by_imdb2[0].episode == 3

    by_season = repo.list_entries(season=2)
    assert len(by_season) == 1

    by_infohash = repo.list_entries(infohash="a" * 40)
    assert len(by_infohash) == 1

    by_search = repo.list_entries(search="tt1111")
    assert len(by_search) == 1


def test_entry_has_timestamp(repo: WhitelistRepository):
    before = time.time()
    e = repo.add_entry("a" * 40, "tt1111111")
    after = time.time()
    assert before <= e.created_at <= after
