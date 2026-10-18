import json
import os
import unittest
from unittest.mock import patch
from model_services import load_services


class CloudConfigTests(unittest.TestCase):
    def test_inline_config_overrides_machine_specific_path(self):
        entry = dict(id="demo", name="Demo", provider="Demo", base_url="https://example.invalid/v1", model="demo", key_env="DEMO_KEY")
        with patch.dict(os.environ, {"MODEL_SERVICES_JSON": json.dumps([entry]), "MODEL_SERVICES_CONFIG": "/not/on/cloud"}, clear=True):
            services = load_services()
            self.assertEqual(services[0].id, "demo")
            self.assertFalse(services[0].configured)

    def test_invalid_inline_config_never_falls_back(self):
        for raw in ["invalid", "[]", "{}", '[{"base_url":"http://example.invalid"}]']:
            with self.subTest(raw=raw), patch.dict(os.environ, {"MODEL_SERVICES_JSON": raw, "TENCENT_API_BASE_URL": "https://example.invalid/v1"}, clear=True):
                with self.assertRaisesRegex(ValueError, "配置无效"):
                    load_services()


if __name__ == "__main__":
    unittest.main()
