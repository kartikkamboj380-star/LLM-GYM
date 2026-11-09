"""Email adapters. Only the mock provider is exposed by the default web UI."""

from .base import EmailMessage, EmailProvider, Inbox
from .mock import MockEmailProvider
from .parser import VerificationCodeParser

__all__ = ["EmailMessage", "EmailProvider", "Inbox", "MockEmailProvider", "VerificationCodeParser"]
