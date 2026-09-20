from pathlib import Path

import pytest

from aniz_pipeline.models import infer_release
from aniz_pipeline.state import StateStore


def test_infer_release():
    release = infer_release("[SubsPlease] One Piece - 1090 [1080p] [WEB-DL].mkv", "magnet:?xt=urn:btih:ABC123")
    assert release.anime_title == "One Piece"
    assert release.episode_number == 1090
    assert release.quality == "1080p"
    assert release.file_format == "mkv"
    assert release.magnet_hash == "abc123"


@pytest.mark.asyncio
async def test_state_claim_is_idempotent(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite3")
    await store.open()
    try:
        assert await store.claim("hash", "title")
        assert not await store.claim("hash", "title")
        assert await store.seen("hash")
        await store.mark("hash", "COMPLETED")
    finally:
        await store.close()
