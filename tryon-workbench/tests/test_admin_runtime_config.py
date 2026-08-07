import unittest
from unittest.mock import patch

from app import admin_runtime_config


class RuntimeStatusTests(unittest.TestCase):
    def test_status_returns_unavailable_instead_of_raising(self):
        with patch.object(
            admin_runtime_config,
            "resolve_tryon_runtime_config",
            side_effect=ModuleNotFoundError("sqlalchemy"),
        ):
            self.assertEqual(
                admin_runtime_config.get_tryon_runtime_status(),
                {
                    "tryon_enabled": False,
                    "configured": False,
                    "available_models": [],
                    "config_source": "unavailable",
                },
            )

    def test_status_reports_admin_database_configuration(self):
        with patch.object(
            admin_runtime_config,
            "resolve_tryon_runtime_config",
            return_value={
                "enabled": True,
                "api_key": "unit-test-placeholder",  # pragma: allowlist secret
                "flash_model": "flash-model",
                "pro_model": "pro-model",
                "source": "admin_db",
            },
        ):
            self.assertEqual(
                admin_runtime_config.get_tryon_runtime_status(),
                {
                    "tryon_enabled": True,
                    "configured": True,
                    "available_models": ["flash", "pro"],
                    "config_source": "admin_db",
                },
            )


if __name__ == "__main__":
    unittest.main()
