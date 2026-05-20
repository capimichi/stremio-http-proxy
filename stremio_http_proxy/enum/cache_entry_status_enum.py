from enum import StrEnum


class CacheEntryStatusEnum(StrEnum):
    MISSING = "missing"
    QUEUED = "queued"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"
