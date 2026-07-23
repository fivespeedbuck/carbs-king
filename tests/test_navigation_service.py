import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from navigation_service import reset_transient_navigation_state  # noqa: E402


class NavigationStateTests(unittest.TestCase):
    def test_leaving_profile_closes_achievement_ui_without_losing_data(self):
        state = {
            "achievements_expanded": True,
            "selected_achievement": "volume_1000",
            "achievement_progress": {"volume_1000": 0.8},
            "weight": "70",
        }
        reset_transient_navigation_state(state, "me", "data")
        self.assertFalse(state["achievements_expanded"])
        self.assertNotIn("selected_achievement", state)
        self.assertEqual(state["achievement_progress"], {"volume_1000": 0.8})
        self.assertEqual(state["weight"], "70")

    def test_staying_on_profile_keeps_current_preview_state(self):
        state = {"achievements_expanded": True}
        reset_transient_navigation_state(state, "me", "me")
        self.assertTrue(state["achievements_expanded"])


if __name__ == "__main__":
    unittest.main()
