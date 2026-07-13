import unittest

from retcon.generators.python import _to_pascal_case, _to_snake_case
from retcon.schema.converter import _to_pascal_case_simple


class PascalCaseConversionTests(unittest.TestCase):
    def test_preserves_camel_case_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("loginAttempt"), "LoginAttempt")

    def test_preserves_existing_word_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("service_events"), "ServiceEvents")

    def test_splits_acronym_boundaries(self) -> None:
        self.assertEqual(_to_pascal_case_simple("userID"), "UserId")

    def test_preserves_compound_acronyms_in_python_names(self) -> None:
        self.assertEqual(_to_snake_case("OAuth2Callback"), "oauth2_callback")
        self.assertEqual(_to_snake_case("GetIPsResponse"), "get_ips_response")
        self.assertEqual(_to_pascal_case("oauth2_callback"), "OAuth2Callback")


if __name__ == "__main__":
    unittest.main()
