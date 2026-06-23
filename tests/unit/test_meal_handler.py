"""
Unit tests for bot/handlers/meal.py — media group buffering helpers.

These test the pure helper functions only (no Telegram context required).
"""

import pytest
from cachetools import TTLCache

from bot.handlers.meal import buffer_photo, get_buffered_photos, is_new_media_group


class TestBufferPhoto:
    def test_buffer_photo_adds_to_cache(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group1", "file_abc", cache)
        assert cache["media_group:group1"] == ["file_abc"]

    def test_buffer_multiple_photos_same_group(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group1", "file_abc", cache)
        buffer_photo("group1", "file_def", cache)
        buffer_photo("group1", "file_ghi", cache)
        assert cache["media_group:group1"] == ["file_abc", "file_def", "file_ghi"]

    def test_buffer_photo_different_groups_independent(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group1", "file_a", cache)
        buffer_photo("group2", "file_b", cache)
        assert cache["media_group:group1"] == ["file_a"]
        assert cache["media_group:group2"] == ["file_b"]


class TestGetBufferedPhotos:
    def test_get_buffered_photos_returns_list(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group1", "file_abc", cache)
        result = get_buffered_photos("group1", cache)
        assert isinstance(result, list)
        assert result == ["file_abc"]

    def test_get_buffered_photos_empty_when_not_buffered(self):
        cache = TTLCache(maxsize=100, ttl=60)
        result = get_buffered_photos("nonexistent_group", cache)
        assert result == []

    def test_get_buffered_photos_returns_all_photos(self):
        cache = TTLCache(maxsize=100, ttl=60)
        file_ids = ["file_1", "file_2", "file_3"]
        for fid in file_ids:
            buffer_photo("group1", fid, cache)
        assert get_buffered_photos("group1", cache) == file_ids


class TestIsNewMediaGroup:
    def test_is_new_media_group_true_when_not_in_cache(self):
        cache = TTLCache(maxsize=100, ttl=60)
        assert is_new_media_group("brand_new_group", cache) is True

    def test_is_new_media_group_false_when_already_buffered(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("existing_group", "file_abc", cache)
        assert is_new_media_group("existing_group", cache) is False

    def test_is_new_media_group_different_groups_independent(self):
        cache = TTLCache(maxsize=100, ttl=60)
        buffer_photo("group1", "file_a", cache)
        # group2 is still new
        assert is_new_media_group("group2", cache) is True
        # group1 is no longer new
        assert is_new_media_group("group1", cache) is False
