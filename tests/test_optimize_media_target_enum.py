from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum


def test_optimize_media_target_enum_values():
    assert OptimizeMediaTargetEnum.COMPATIBLE == "compatible"
    assert OptimizeMediaTargetEnum.WEB_READY_MP4 == "web_ready_mp4"
    assert OptimizeMediaTargetEnum.NONE == "none"


def test_optimize_media_target_enum_from_str():
    assert OptimizeMediaTargetEnum.from_str(None) == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("compatible") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("COMPATIBLE") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("web_ready_mp4") == OptimizeMediaTargetEnum.WEB_READY_MP4
    assert OptimizeMediaTargetEnum.from_str("web_ready") == OptimizeMediaTargetEnum.WEB_READY_MP4
    assert OptimizeMediaTargetEnum.from_str("none") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("disabled") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("false") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("unknown_val") == OptimizeMediaTargetEnum.COMPATIBLE
