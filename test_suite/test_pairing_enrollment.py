import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from enroll_pairing import enroll


class TrustedPairingTests(unittest.TestCase):
    def test_create_only_and_refuse_replacing_physical_identity(self):
        binding = {"deviceId": "ab12cd", "pairingCode": "a" * 64}
        cloud = Mock()
        cloud.call.side_effect = [HTTPError("https://example.test", 404, "missing", {}, None), {}]
        enroll(cloud, binding)
        self.assertEqual(cloud.call.call_args.args[1], "POST")
        cloud.call.side_effect = None
        cloud.call.return_value = {"fields": {"pairingCode": {"stringValue": "b" * 64}}}
        with self.assertRaisesRegex(ValueError, "refusing replacement"):
            enroll(cloud, binding)
        self.assertEqual(len(cloud.call.call_args.args), 1)


if __name__ == "__main__":
    unittest.main()
