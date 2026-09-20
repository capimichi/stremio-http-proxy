import pytest

from stremio_http_proxy.entity.cache_entry import Base
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.client.tmdb_client import TMDBClient


@pytest.fixture
def db_manager(tmp_path):
    sqlite_file = tmp_path / "test_media.sqlite"
    return DbManager(str(sqlite_file))


@pytest.fixture
def media_repo(db_manager):
    return MediaRepository(db_manager)


@pytest.fixture
def metadata_service(media_repo, tmp_path):
    logger_factory = LoggerFactory(str(tmp_path / "logs"))
    tmdb_client = TMDBClient(api_key=None)
    return MediaMetadataService(media_repo, tmdb_client, logger_factory)


def test_media_repository_upsert_and_get(media_repo):
    media = media_repo.upsert_media(
        media_id="tt0903747",
        media_type="series",
        title="Breaking Bad",
        year="2008",
        poster="https://image.tmdb.org/t/p/w500/bb.jpg",
        overview="A high school chemistry teacher...",
    )
    assert media.id == "tt0903747"
    assert media.title == "Breaking Bad"

    # Fetch
    fetched = media_repo.get_media("tt0903747")
    assert fetched is not None
    assert fetched.year == "2008"

    # Upsert item
    item = media_repo.upsert_media_item(
        item_id="tt0903747:1:1",
        media_id="tt0903747",
        season=1,
        episode=1,
        title="Pilot",
    )
    assert item.id == "tt0903747:1:1"
    assert item.season == 1
    assert item.episode == 1

    items = media_repo.get_items_for_media("tt0903747")
    assert len(items) == 1
    assert items[0].title == "Pilot"


def test_media_metadata_service_parse_content_id(metadata_service):
    media_id, item_id, season, episode, mtype = metadata_service.parse_content_id("tt0903747:2:5", "series")
    assert media_id == "tt0903747"
    assert item_id == "tt0903747:2:5"
    assert season == 2
    assert episode == 5
    assert mtype == "series"

    movie_id, movie_item, m_s, m_e, movie_type = metadata_service.parse_content_id("tt0137523", "movie")
    assert movie_id == "tt0137523"
    assert movie_item == "tt0137523"
    assert m_s is None
    assert m_e is None
    assert movie_type == "movie"


def test_media_metadata_clean_raw_title(metadata_service):
    raw = "Gotham.S01E01.1080p.HDTV.x264-LOL"
    cleaned = metadata_service.clean_raw_title(raw)
    assert cleaned.startswith("Gotham S01E01")
    assert "HDTV" not in cleaned
    assert "x264" not in cleaned


def test_media_metadata_ensure_media_and_item(metadata_service, media_repo):
    media, item = metadata_service.ensure_media_and_item(
        content_id="tt3749900:1:1",
        content_type="series",
        fallback_title="Gotham.S01E01.1080p",
        fallback_poster="https://example.com/poster.jpg",
        schedule_enrichment=False,
    )
    assert media.id == "tt3749900"
    assert item.id == "tt3749900:1:1"
    assert item.season == 1
    assert item.episode == 1

    # Check that repo has it
    saved_media = media_repo.get_media("tt3749900")
    assert saved_media is not None
    assert "Gotham" in saved_media.title
