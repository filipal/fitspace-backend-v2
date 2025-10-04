import unittest
from unittest.mock import patch

from werkzeug.exceptions import HTTPException

from avatar import routes


class ApplyPayloadTests(unittest.TestCase):
    def setUp(self):
        self.user_id = "user-123"
        self.user_context = {"session_id": "session-abc"}

    @patch("avatar.routes.repository.create_avatar")
    def test_create_with_extended_metadata(self, mock_create):
        expected_avatar = {"id": "avatar-1"}
        mock_create.return_value = expected_avatar

        payload = {
            "name": "Runner",
            "gender": "Female",
            "ageRange": "Adult",
            "creationMode": "Manual",
            "source": "Web",
            "quickMode": True,
            "createdBySession": "session-xyz",
            "quickModeSettings": {
                "bodyShape": "Hourglass",
                "athleticLevel": "High",
                "measurements": {"waistCircumference": 70.5},
            },
        }

        result = routes._apply_payload(
            self.user_id,
            payload,
            user_context=self.user_context,
        )

        self.assertIs(result, expected_avatar)
        mock_create.assert_called_once_with(
            self.user_id,
            name="Runner",
            gender="female",
            age_range="adult",
            creation_mode="manual",
            source="web",
            quick_mode=True,
            created_by_session="session-xyz",
            basic_measurements={},
            body_measurements={},
            morph_targets=[],
            quick_mode_settings={
                "bodyShape": "hourglass",
                "athleticLevel": "high",
                "measurements": {"waistCircumference": 70.5},
            },
            user_context=self.user_context,
        )

    @patch("avatar.routes.repository.create_avatar")
    def test_creation_mode_extracted_from_measurements(self, mock_create):
        expected_avatar = {"id": "avatar-3"}
        mock_create.return_value = expected_avatar

        payload = {
            "name": "Walker",
            "basicMeasurements": {"height": 172.4, "creationMode": "Preset"},
            "bodyMeasurements": {"chest": 95.2},
        }

        result = routes._apply_payload(
            self.user_id,
            payload,
            user_context=None,
        )

        self.assertIs(result, expected_avatar)
        mock_create.assert_called_once_with(
            self.user_id,
            name="Walker",
            gender=None,
            age_range=None,
            creation_mode="preset",
            source=None,
            quick_mode=False,
            created_by_session=None,
            basic_measurements={"height": 172.4},
            body_measurements={"chest": 95.2},
            morph_targets=[],
            quick_mode_settings=None,
            user_context=None,
        )

    @patch("avatar.routes.repository.create_avatar")
    def test_quick_mode_settings_enable_flag(self, mock_create):
        expected_avatar = {"id": "avatar-4"}
        mock_create.return_value = expected_avatar

        payload = {
            "name": "Sprinter",
            "quickModeSettings": {
                "bodyShape": "Pear",
                "measurements": {"hipCircumference": 102.3},
            },
        }

        result = routes._apply_payload(
            self.user_id,
            payload,
            user_context=None,
        )

        self.assertIs(result, expected_avatar)
        mock_create.assert_called_once_with(
            self.user_id,
            name="Sprinter",
            gender=None,
            age_range=None,
            creation_mode=None,
            source=None,
            quick_mode=True,
            created_by_session=None,
            basic_measurements={},
            body_measurements={},
            morph_targets=[],
            quick_mode_settings={
                "bodyShape": "pear",
                "measurements": {"hipCircumference": 102.3},
            },
            user_context=None,
        )

    @patch("avatar.routes.repository.create_avatar")
    def test_ui_age_range_label_is_accepted(self, mock_create):
        expected_avatar = {"id": "avatar-ui"}
        mock_create.return_value = expected_avatar

        payload = {
            "name": "Marathoner",
            "ageRange": "20-29",
        }

        result = routes._apply_payload(
            self.user_id,
            payload,
            user_context=None,
        )

        self.assertIs(result, expected_avatar)
        mock_create.assert_called_once_with(
            self.user_id,
            name="Marathoner",
            gender=None,
            age_range="20-29",
            creation_mode=None,
            source=None,
            quick_mode=False,
            created_by_session=None,
            basic_measurements={},
            body_measurements={},
            morph_targets=[],
            quick_mode_settings=None,
            user_context=None,
        )

    @patch("avatar.routes.repository.update_avatar")
    def test_update_defaults_and_validation(self, mock_update):
        expected_avatar = {"id": "avatar-2"}
        mock_update.return_value = expected_avatar

        payload = {
            "name": "  Explorer  ",
            "quickMode": False,
        }

        result = routes._apply_payload(
            self.user_id,
            payload,
            avatar_id="00000000-0000-0000-0000-000000000001",
            user_context=None,
        )

        self.assertIs(result, expected_avatar)
        mock_update.assert_called_once_with(
            self.user_id,
            "00000000-0000-0000-0000-000000000001",
            name="  Explorer  ",
            gender=None,
            age_range=None,
            creation_mode=None,
            source=None,
            quick_mode=False,
            created_by_session=None,
            basic_measurements={},
            body_measurements={},
            morph_targets=[],
            quick_mode_settings=None,
            user_context=None,
        )

    def test_invalid_gender_rejected(self):
        payload = {"gender": "unknown"}

        with self.assertRaises(HTTPException) as ctx:
            routes._apply_payload(self.user_id, payload)

        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("gender", ctx.exception.description)

    def test_invalid_quick_mode_type(self):
        payload = {"quickMode": "yes"}

        with self.assertRaises(HTTPException) as ctx:
            routes._apply_payload(self.user_id, payload)

        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("quickMode", ctx.exception.description)

    def test_invalid_quick_mode_measurements(self):
        payload = {"quickModeSettings": {"measurements": {"waist": "n/a"}}}

        with self.assertRaises(HTTPException) as ctx:
            routes._apply_payload(self.user_id, payload)

        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("quickModeSettings.measurements", ctx.exception.description)

    def test_conflicting_creation_mode_values_rejected(self):
        payload = {
            "creationMode": "Manual",
            "basicMeasurements": {"creationMode": "Scan"},
        }

        with self.assertRaises(HTTPException) as ctx:
            routes._apply_payload(self.user_id, payload)

        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("creationMode", ctx.exception.description)

if __name__ == "__main__":
    unittest.main()