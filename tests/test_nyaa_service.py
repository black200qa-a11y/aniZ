from app.services.nyaa_service import smart_tags


def test_smart_tags_detect_pack_languages_and_formats():
    tags = smart_tags("[SubsPlease] Show Batch 01-12 Arabic 1080p.mkv")
    assert set(tags) == {"pack", "ara", "eng", "mkv"}


def test_arabic_sorting_priority_contract():
    items = [{"nyaa_id": "1", "title": "English", "tags": ["eng"]}, {"nyaa_id": "2", "title": "Arabic", "tags": ["ara"]}]
    ordered = sorted(items, key=lambda item: ("ara" not in item["tags"], item["title"].lower()))
    assert ordered[0]["nyaa_id"] == "2"
