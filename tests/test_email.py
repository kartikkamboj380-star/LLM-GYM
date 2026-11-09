import unittest

from app.email import MockEmailProvider, VerificationCodeParser


class VerificationParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = VerificationCodeParser()

    def test_numeric_code(self):
        self.assertEqual("483920", self.parser.extract("Your verification code is 483920. It expires soon."))

    def test_alphanumeric_code_is_normalized(self):
        self.assertEqual("T4K9Q2", self.parser.extract("Your one-time code: t4k9q2"))

    def test_arbitrary_number_and_word_are_ignored(self):
        self.assertIsNone(self.parser.extract("Order 123456 was delivered in 2026."))
        self.assertIsNone(self.parser.extract("Verification code is SECRET"))

    def test_context_is_required(self):
        self.assertIsNone(self.parser.extract("ABC123 is a part number"))


class MockEmailTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockEmailProvider()
        self.inbox = self.provider.create_inbox()

    def test_inbox_uses_reserved_domain(self):
        self.assertTrue(self.inbox.address.endswith("@example.test"))
        self.assertEqual([], self.provider.get_messages(self.inbox.id))

    def test_numeric_demo_can_be_polled(self):
        message = self.provider.send_demo_verification(self.inbox.id, "numeric")
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0)
        self.assertTrue(result["found"])
        self.assertRegex(result["code"], r"^\d{6}$")
        self.assertEqual(message.id, result["message_id"])

    def test_alphanumeric_demo_can_be_polled(self):
        self.provider.send_demo_verification(self.inbox.id, "alphanumeric")
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0)
        self.assertTrue(result["found"])
        self.assertRegex(result["code"], r"^[A-Z0-9]{6}$")

    def test_empty_poll_returns_without_fixed_delay(self):
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0)
        self.assertFalse(result["found"])
        self.assertEqual(1, result["attempts"])

    def test_poll_configuration_is_bounded(self):
        with self.assertRaises(ValueError):
            self.provider.poll_for_code(self.inbox.id, timeout_seconds=61)
        with self.assertRaises(ValueError):
            self.provider.poll_for_code(self.inbox.id, interval_seconds=0)

    def test_unknown_inbox_and_invalid_demo_are_rejected(self):
        with self.assertRaises(KeyError):
            self.provider.get_messages("missing")
        with self.assertRaises(ValueError):
            self.provider.send_demo_verification(self.inbox.id, "unknown")


if __name__ == "__main__":
    unittest.main()
