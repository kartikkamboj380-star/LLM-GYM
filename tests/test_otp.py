import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from app.email import (
    AmbiguousCodeError,
    EmailMessage,
    EmailProvider,
    EmailProviderRateLimit,
    ExpiredCodeError,
    MockEmailProvider,
    OTPRules,
    VerificationCodeParser,
    sanitize_poll_result,
)
from app.providers.base import ProviderError


def iso(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def message(text="Your verification code is 123456", **kwargs):
    now = datetime.now(timezone.utc)
    values = {
        "id": kwargs.pop("id", "message-1"),
        "inbox_id": "inbox-1",
        "sender": "verification@example.test",
        "subject": "LLM-GYM test",
        "text": text,
        "received_at": iso(now),
        "expires_at": iso(now + timedelta(minutes=10)),
        "html": None,
    }
    values.update(kwargs)
    return EmailMessage(**values)


class OTPParserRuleTests(unittest.TestCase):
    def setUp(self):
        self.parser = VerificationCodeParser()

    def test_four_six_and_eight_digit_codes(self):
        for code in ("1234", "123456", "12345678"):
            with self.subTest(code=code):
                self.assertEqual(code, self.parser.extract(f"Your verification code is {code}"))

    def test_code_surrounded_by_text_and_html(self):
        self.assertEqual("A1B2C3", self.parser.extract("Welcome! Your confirmation code: A1B2C3. Goodbye"))
        self.assertEqual(
            "H7K2P9",
            self.parser.extract("", "<html><body><p>Your <strong>verification code</strong> is H7K2P9</p></body></html>"),
        )
        self.assertIsNone(self.parser.extract("", "<script>verification code is A1B2C3</script>"))

    def test_multiple_distinct_codes_are_ambiguous(self):
        with self.assertRaises(AmbiguousCodeError):
            self.parser.extract("Verification code is 123456. Confirmation code is 654321")

    def test_duplicate_code_is_not_ambiguous(self):
        self.assertEqual("123456", self.parser.extract("Verification code is 123456. OTP: 123456"))

    def test_expected_length_disambiguates_candidates(self):
        rules = OTPRules(expected_length=4)
        self.assertEqual("1234", self.parser.extract("Verification code is 123456. Confirmation code is 1234", rules=rules))

    def test_allowed_characters_are_configurable(self):
        rules = OTPRules(allowed_characters="ABC123")
        self.assertIsNone(self.parser.extract("Verification code is Z9Z9Z9", rules=rules))

    def test_expired_message_and_old_message_are_rejected(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ExpiredCodeError):
            self.parser.extract_from_message(message(expires_at=iso(now - timedelta(seconds=1))), now=now)
        old = iso(now - timedelta(minutes=20))
        with self.assertRaises(ExpiredCodeError):
            self.parser.extract_from_message(message(received_at=old), OTPRules(max_age_seconds=60), now=now)

    def test_wrong_sender_and_subject_are_ignored(self):
        self.assertIsNone(self.parser.extract_from_message(message(), OTPRules(sender="other@example.test")))
        self.assertIsNone(self.parser.extract_from_message(message(), OTPRules(subject="different-app")))

    def test_expected_application_and_test_run_context(self):
        rules = OTPRules(expected_application="LLM-GYM", expected_test_run="run-42")
        self.assertIsNone(self.parser.extract_from_message(message(), rules))
        contextual = message("LLM-GYM run-42 verification code is 123456")
        self.assertEqual("123456", self.parser.extract_from_message(contextual, rules))

    def test_invalid_encoding_and_timestamp_are_controlled_errors(self):
        with self.assertRaises(ValueError):
            self.parser.extract(b"\xff\xfe")
        with self.assertRaises(ValueError):
            self.parser.extract_from_message(message(received_at="not-a-time"))

    def test_redaction_removes_otp_but_preserves_safe_context(self):
        sanitized = self.parser.redact("Your verification code is 123456. It expires soon.")
        self.assertNotIn("123456", sanitized)
        self.assertIn("[REDACTED]", sanitized)
        self.assertIn("expires soon", sanitized)


class MockLifecycleAndPollingTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockEmailProvider()
        self.inbox = self.provider.create_inbox(local_part="predictable-test")

    def test_capabilities_health_info_and_specific_message(self):
        self.assertEqual("predictable-test@example.test", self.inbox.address)
        self.assertFalse(self.provider.capabilities()["real_delivery"])
        self.assertEqual("ok", self.provider.health()["status"])
        sent = self.provider.send_demo_verification(self.inbox.id)
        self.assertEqual("message_received", self.provider.get_inbox(self.inbox.id).status)
        self.assertEqual(sent.id, self.provider.get_message(self.inbox.id, sent.id).id)
        self.assertNotIn("text", sent.sanitized_dict())

    def test_expired_inbox_stops_polling_and_rejects_delivery(self):
        expired = self.provider.create_inbox(ttl_seconds=0)
        result = self.provider.poll_for_code(expired.id, timeout_seconds=60)
        self.assertEqual("expired", result["status"])
        self.assertEqual(0, result["attempts"])
        with self.assertRaises(ExpiredCodeError):
            self.provider.send_demo_verification(expired.id)

    def test_delete_stops_lifecycle(self):
        deleted = self.provider.delete_inbox(self.inbox.id)
        self.assertEqual("deleted", deleted.status)
        with self.assertRaises(KeyError):
            self.provider.get_inbox(self.inbox.id)

    def test_provider_error_rate_limit_and_timeout_simulation(self):
        self.provider.set_failure_mode(self.inbox.id, "provider_error")
        with self.assertRaises(ProviderError):
            self.provider.get_messages(self.inbox.id)
        self.assertEqual("degraded", self.provider.health()["status"])
        self.provider.set_failure_mode(self.inbox.id, "rate_limit")
        with self.assertRaises(EmailProviderRateLimit):
            self.provider.get_messages(self.inbox.id)
        self.provider.set_failure_mode(self.inbox.id, "timeout")
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0.01)
        self.assertEqual("timeout", result["status"])

    def test_pre_cancelled_poll_has_clear_final_status(self):
        cancellation = threading.Event()
        cancellation.set()
        result = EmailProvider.poll_for_code(self.provider, self.inbox.id, timeout_seconds=10, cancel_event=cancellation)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(0, result["attempts"])

    def test_active_poll_can_be_cancelled_and_sanitized(self):
        self.provider.send_demo_verification(self.inbox.id)
        # Remove the delivered code to keep polling active until cancellation.
        self.provider._messages[self.inbox.id] = []
        outcome = []

        def run():
            outcome.append(self.provider.poll_for_code(self.inbox.id, timeout_seconds=10, interval_seconds=0.1))

        thread = threading.Thread(target=run)
        thread.start()
        deadline = time.monotonic() + 2
        while self.inbox.id not in self.provider._cancel_events and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.provider.cancel_poll(self.inbox.id))
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual("cancelled", outcome[0]["status"])
        sanitized = sanitize_poll_result(outcome[0])
        self.assertNotIn("code", sanitized)
        self.assertNotIn("text", str(sanitized))

    def test_sanitized_report_never_contains_otp_or_message_body(self):
        message = self.provider.send_demo_verification(self.inbox.id)
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0)
        sanitized = sanitize_poll_result(result)
        self.assertTrue(sanitized["code_detected"])
        self.assertNotIn(result["code"], str(sanitized))
        self.assertNotIn(message.text, str(sanitized))
        self.assertEqual([message.id], [item["id"] for item in sanitized["messages"]])

    def test_distinct_codes_across_messages_are_not_arbitrarily_selected(self):
        self.provider.send_message(self.inbox.id, "verification@example.test", "One", "Verification code is 111111")
        self.provider.send_message(self.inbox.id, "verification@example.test", "Two", "Verification code is 222222")
        result = self.provider.poll_for_code(self.inbox.id, timeout_seconds=0)
        self.assertEqual("ambiguous", result["status"])
        self.assertIsNone(result["code"])
        self.assertNotIn("111111", result["error"])

    def test_backoff_and_failure_mode_validation(self):
        with self.assertRaises(ValueError):
            self.provider.poll_for_code(self.inbox.id, backoff_multiplier=3)
        with self.assertRaises(ValueError):
            self.provider.set_failure_mode(self.inbox.id, "unsupported")


if __name__ == "__main__":
    unittest.main()
