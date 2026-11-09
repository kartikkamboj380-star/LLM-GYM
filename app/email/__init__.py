"""Email adapters. Only the mock provider is exposed by the default web UI."""

from .base import EmailMessage, EmailProvider, EmailProviderRateLimit, Inbox, sanitize_poll_result
from .mock import MockEmailProvider
from .parser import AmbiguousCodeError, ExpiredCodeError, OTPRules, VerificationCodeParser

__all__ = [
    "AmbiguousCodeError",
    "EmailMessage",
    "EmailProvider",
    "EmailProviderRateLimit",
    "ExpiredCodeError",
    "Inbox",
    "MockEmailProvider",
    "OTPRules",
    "VerificationCodeParser",
    "sanitize_poll_result",
]
