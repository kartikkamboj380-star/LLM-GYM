import unittest
from unittest.mock import patch

from app.errors import APIError
from app.rate_limit import InMemoryRateLimiter


class RateLimitTests(unittest.TestCase):
    def test_limit_is_per_bucket_and_identity(self):
        limiter = InMemoryRateLimiter()
        with patch("app.rate_limit.time.monotonic", return_value=100):
            limiter.enforce("chat", "phone", 2, 60)
            limiter.enforce("chat", "phone", 2, 60)
            with self.assertRaises(APIError) as caught:
                limiter.enforce("chat", "phone", 2, 60)
            limiter.enforce("chat", "other", 2, 60)
            limiter.enforce("email", "phone", 2, 60)
        self.assertEqual(429, caught.exception.status)
        self.assertEqual("RATE_LIMITED", caught.exception.code)
        self.assertEqual(60, caught.exception.retry_after)

    def test_window_expires_and_retry_after_decreases(self):
        limiter = InMemoryRateLimiter()
        with patch("app.rate_limit.time.monotonic", return_value=100):
            limiter.enforce("chat", "phone", 1, 10)
        with patch("app.rate_limit.time.monotonic", return_value=104):
            with self.assertRaises(APIError) as caught:
                limiter.enforce("chat", "phone", 1, 10)
            self.assertEqual(6, caught.exception.retry_after)
        with patch("app.rate_limit.time.monotonic", return_value=111):
            limiter.enforce("chat", "phone", 1, 10)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            InMemoryRateLimiter().enforce("chat", "phone", 0, 60)
        with self.assertRaises(ValueError):
            InMemoryRateLimiter().enforce("chat", "phone", 1, 0)


if __name__ == "__main__":
    unittest.main()
