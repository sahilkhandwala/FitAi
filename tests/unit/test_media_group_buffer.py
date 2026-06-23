"""
Unit tests for TTLCache-based media group buffer behavior.

Tests that the shared media_buffer from bot/handlers/meal.py
uses the correct key format and correctly isolates groups.
"""

import pytest
from cachetools import TTLCache

from bot.handlers.meal import buffer_photo, get_buffered_photos, is_new_media_group


class TestMediaGroupBufferGrouping:
    def test_two_photos_same_group_are_grouped_together(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("abc123", "file_1", cache)
        buffer_photo("abc123", "file_2", cache)
        photos = get_buffered_photos("abc123", cache)
        assert len(photos) == 2
        assert "file_1" in photos
        assert "file_2" in photos

    def test_photos_different_group_ids_are_separate(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group_a", "file_1", cache)
        buffer_photo("group_b", "file_2", cache)
        assert get_buffered_photos("group_a", cache) == ["file_1"]
        assert get_buffered_photos("group_b", cache) == ["file_2"]

    def test_cache_key_format_is_media_group_prefix(self):
        """Key must be 'media_group:{id}' — not the raw group id."""
        cache = TTLCache(maxsize=100, ttl=60)
        group_id = "xyz789"
        buffer_photo(group_id, "file_abc", cache)
        assert f"media_group:{group_id}" in cache
        # Raw group id should NOT be a key
        assert group_id not in cache

    def test_is_new_before_any_buffering(self):
        cache = TTLCache(maxsize=100, ttl=60)
        assert is_new_media_group("fresh_group", cache) is True

    def test_is_not_new_after_first_buffer(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("existing_group", "file_a", cache)
        assert is_new_media_group("existing_group", cache) is False
