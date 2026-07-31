from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.password_crypto import (
    PasswordCryptoError,
    decrypt_password,
    encrypt_password,
    is_encrypted_password,
    reveal_password,
    seal_password,
)
from src.config_loader import ConfigLoader


class PasswordCryptoTest(unittest.TestCase):
    def test_roundtrip(self):
        mid = "test-machine-id-aaaa-bbbb"
        plain = "s3cret-密码"
        enc = encrypt_password(plain, machine_id=mid)
        self.assertTrue(is_encrypted_password(enc))
        self.assertTrue(enc.startswith("enc:v1:"))
        self.assertNotIn(plain, enc)
        self.assertEqual(decrypt_password(enc, machine_id=mid), plain)

    def test_seal_idempotent(self):
        mid = "machine-xyz"
        once = seal_password("abc", machine_id=mid)
        twice = seal_password(once, machine_id=mid)
        self.assertEqual(once, twice)
        self.assertEqual(reveal_password(twice, machine_id=mid), "abc")

    def test_reveal_plaintext_passthrough(self):
        self.assertEqual(reveal_password("plain-old", machine_id="m"), "plain-old")

    def test_wrong_machine_fails(self):
        enc = encrypt_password("pw", machine_id="host-a")
        with self.assertRaises(PasswordCryptoError):
            decrypt_password(enc, machine_id="host-b")

    def test_empty(self):
        self.assertEqual(encrypt_password("", machine_id="m"), "")
        self.assertEqual(decrypt_password("", machine_id="m"), "")


class ConfigPasswordIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "config.yaml"
        # 绕过单例：直接构造原始对象
        self.loader = object.__new__(ConfigLoader)
        self.loader._config_path = self.cfg_path
        self.loader._yaml = ConfigLoader._yaml
        self.loader._config_data = {
            "account": {"username": "u@example.com", "password": "plain-pass"},
            "download": {"dir": "downloads"},
            "log": {"level": "INFO"},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_upgrade_and_get_set(self):
        mid = "unit-test-machine"
        with (
            patch("src.password_crypto.machineid.id", return_value=mid),
            patch(
                "src.config_loader.seal_password",
                side_effect=lambda v, machine_id=None: seal_password(v, machine_id=mid),
            ),
            patch(
                "src.config_loader.reveal_password",
                side_effect=lambda v, machine_id=None: reveal_password(
                    v, machine_id=mid
                ),
            ),
            patch(
                "src.config_loader.is_encrypted_password",
                side_effect=is_encrypted_password,
            ),
        ):
            self.assertTrue(self.loader._upgrade_plaintext_password())
            stored = self.loader._raw_account()["password"]
            self.assertTrue(is_encrypted_password(stored))
            self.assertEqual(self.loader.get_password(), "plain-pass")
            self.assertEqual(self.loader.account["password"], "plain-pass")
            self.assertEqual(self.loader.get("account.password"), "plain-pass")

            self.loader.set("account.password", "new-pass")
            self.assertTrue(
                is_encrypted_password(self.loader._raw_account()["password"])
            )
            self.assertEqual(self.loader.get_password(), "new-pass")

            self.loader.save()
            disk = self.cfg_path.read_text(encoding="utf-8")
            self.assertIn("enc:v1:", disk)
            self.assertNotIn("new-pass", disk)
            self.assertNotIn("plain-pass", disk)


if __name__ == "__main__":
    unittest.main()
