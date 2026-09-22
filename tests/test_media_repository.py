from stremio_http_proxy.helper.content_id_helper import parse_content_id
import pytest

from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository
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
def media_item_repo(db_manager):
    return MediaItemRepository(db_manager)

@pytest.fixture
def metadata_service(media_repo, media_item_repo, tmp_path):
    logger_factory = LoggerFactory(str(tmp_path / "logs"))
    tmdb_client = TMDBClient(api_key=None)
    return MediaMetadataService(media_repo, media_item_repo, tmdb_client, logger_factory)


def test_media_repository_upsert_and_get(media_repo, media_item_repo):
    media = media_repo.upsert_media(
        imdb_id="tt0903747",
        media_type="series",
        title="Breaking Bad",
        year="2008",
        poster="https://image.tmdb.org/t/p/w500/bb.jpg",
        overview="A high school chemistry teacher...",
    )
    assert isinstance(media.id, int)
    assert media.imdb_id == "tt0903747"
    assert media.title == "Breaking Bad"

    # Fetch by id and by imdb_id
    fetched = media_repo.get_media(media.id)
    assert fetched is not None
    assert fetched.year == "2008"

    fetched_by_imdb = media_repo.get_by_imdb_id("tt0903747")
    assert fetched_by_imdb is not None
    assert fetched_by_imdb.id == media.id

    # Upsert item
    item = media_item_repo.upsert_media_item(
        media_id=media.id,
        season=1,
        episode=1,
        title="Pilot",
    )
    assert isinstance(item.id, int)
    assert item.media_id == media.id
    assert item.season == 1
    assert item.episode == 1

    items = media_item_repo.get_items_for_media(media.id)
    assert len(items) == 1
    assert items[0].title == "Pilot"


def test_media_metadata_service_parse_content_id(metadata_service):
    media_id, item_id, season, episode, mtype = parse_content_id("tt0903747:2:5", "series")
    assert media_id == "tt0903747"
    assert item_id == "tt0903747:2:5"
    assert season == 2
    assert episode == 5
    assert mtype == "series"

    movie_id, movie_item, m_s, m_e, movie_type = parse_content_id("tt0137523", "movie")
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
    assert isinstance(media.id, int)
    assert media.imdb_id == "tt3749900"
    assert isinstance(item.id, int)
    assert item.media_id == media.id
    assert item.season == 1
    assert item.episode == 1

    # Check that repo has it
    saved_media = media_repo.get_by_imdb_id("tt3749900")
    assert saved_media is not None
    assert "Gotham" in saved_media.title


def test_media_repository_get_and_ensure_by_content_id_movie(media_item_repo, metadata_service):
    # Not yet created
    assert media_item_repo.get_by_content_id("tt0137523", "movie") is None

    # Ensure creates media and default media_item
    media, item = metadata_service.ensure_media_and_item(
        content_id="tt0137523",
        content_type="movie",
        fallback_title="Fight Club",
    )
    assert item is not None
    assert isinstance(item.id, int)
    assert item.media_id == media.id
    assert item.season is None
    assert item.episode is None

    # Now get_media_item_by_content_id should find it
    found = media_item_repo.get_by_content_id("tt0137523", "movie")
    assert found is not None
    assert found.id == item.id
    assert found.media_id == media.id


def test_media_repository_get_and_ensure_by_content_id_series(media_item_repo, metadata_service):
    # Not yet created
    assert media_item_repo.get_by_content_id("tt4158110:2:11", "series") is None

    # Ensure creates media and episode media_item
    media, item = metadata_service.ensure_media_and_item(
        content_id="tt4158110:2:11",
        content_type="series",
        fallback_title="Mr. Robot S02E11",
    )
    assert item is not None
    assert isinstance(item.id, int)
    assert item.media_id == media.id
    assert item.season == 2
    assert item.episode == 11

    # Now get_media_item_by_content_id should find it
    found = media_item_repo.get_by_content_id("tt4158110:2:11")
    assert found is not None
    assert found.id == item.id
    assert found.season == 2
    assert found.episode == 11
