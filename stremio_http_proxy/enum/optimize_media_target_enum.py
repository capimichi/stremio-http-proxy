from enum import StrEnum


class OptimizeMediaTargetEnum(StrEnum):
    COMPATIBLE = "compatible"
    WEB_READY_MP4 = "web_ready_mp4"
    NONE = "none"

    @classmethod
    def from_str(cls, value: str | None) -> "OptimizeMediaTargetEnum":
        if not value:
            return cls.COMPATIBLE
        val = value.strip().lower()
        if val in ("none", "disabled", "false"):
            return cls.NONE
        if val in ("web_ready", "web_ready_mp4"):
            return cls.WEB_READY_MP4
        try:
            return cls(val)
        except ValueError:
            return cls.COMPATIBLE
