from pathlib import Path

from aniz_pipeline.video_inspector import VideoInspectionError, VideoInspector


def test_video_inspector_picks_largest_video(tmp_path: Path):
    small = tmp_path / "sample.mp4"
    large = tmp_path / "episode.mkv"
    small.write_bytes(b"1")
    large.write_bytes(b"123")
    assert VideoInspector().pick_main_video(tmp_path) == large


def test_video_inspector_requires_supported_video(tmp_path: Path):
    (tmp_path / "readme.txt").write_text("x")
    try:
        VideoInspector().pick_main_video(tmp_path)
    except VideoInspectionError:
        return
    raise AssertionError("expected VideoInspectionError")
