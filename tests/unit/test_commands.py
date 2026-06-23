"""
Unit tests for bot/handlers/commands.py — pure parsing functions.

These test only the deterministic helpers (no Telegram context required).
"""

import pytest

from bot.handlers.commands import parse_profile_update_command, is_skip_comparison_message


class TestParseProfileUpdateCommand:
    def test_calorie_target(self):
        result = parse_profile_update_command("change my calorie target to 2000")
        assert result == {"calorie_target": 2000}

    def test_calorie_target_int_type(self):
        result = parse_profile_update_command("change my calorie target to 1800")
        assert isinstance(result["calorie_target"], int)

    def test_weight_kg(self):
        result = parse_profile_update_command("update my weight to 79")
        assert result == {"weight_kg": 79.0}

    def test_weight_kg_float_type(self):
        result = parse_profile_update_command("update my weight to 79")
        assert isinstance(result["weight_kg"], float)

    def test_activity_level(self):
        result = parse_profile_update_command("change activity level to active")
        assert result == {"activity_level": "active"}

    def test_activity_level_sedentary(self):
        result = parse_profile_update_command("set activity level to sedentary")
        assert result == {"activity_level": "sedentary"}

    def test_step_goal(self):
        result = parse_profile_update_command("change step goal to 8000")
        assert result == {"step_goal": 8000}

    def test_step_goal_int_type(self):
        result = parse_profile_update_command("change step goal to 8000")
        assert isinstance(result["step_goal"], int)

    def test_sleep_goal(self):
        result = parse_profile_update_command("change sleep goal to 8")
        assert result == {"sleep_goal_hrs": 8.0}

    def test_sleep_goal_float_type(self):
        result = parse_profile_update_command("change sleep goal to 8")
        assert isinstance(result["sleep_goal_hrs"], float)

    def test_unparseable_returns_empty_dict(self):
        result = parse_profile_update_command("hello how are you")
        assert result == {}

    def test_empty_string_returns_empty_dict(self):
        result = parse_profile_update_command("")
        assert result == {}

    def test_unrecognized_command_returns_empty_dict(self):
        result = parse_profile_update_command("what is my cholesterol?")
        assert result == {}


class TestIsSkipComparisonMessage:
    def test_skip_comparison_lowercase(self):
        assert is_skip_comparison_message("skip comparison") is True

    def test_skip_comparison_uppercase(self):
        assert is_skip_comparison_message("SKIP COMPARISON") is True

    def test_skip_comparison_mixed_case(self):
        assert is_skip_comparison_message("Skip Comparison") is True

    def test_skip_comparison_with_leading_trailing_whitespace(self):
        assert is_skip_comparison_message("  skip comparison  ") is True

    def test_skip_alone_is_false(self):
        assert is_skip_comparison_message("skip") is False

    def test_comparison_alone_is_false(self):
        assert is_skip_comparison_message("comparison") is False

    def test_partial_phrase_is_false(self):
        assert is_skip_comparison_message("please skip comparison") is False

    def test_empty_string_is_false(self):
        assert is_skip_comparison_message("") is False
