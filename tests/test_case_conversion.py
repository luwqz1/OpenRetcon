import unittest

from retcon.schema.converter import _to_pascal_case_simple


class PascalCaseConversionTests(unittest.TestCase):
    def test_preserves_camel_case_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("loginAttempt"), "LoginAttempt")

    def test_preserves_existing_word_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("service_events"), "ServiceEvents")

    def test_splits_acronym_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("userID"), "UserId")


if __name__ == "__main__":
    unittest.main()
