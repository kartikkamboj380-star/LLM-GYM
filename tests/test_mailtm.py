import unittest
from unittest.mock import patch

from app.email.mailtm import MailTmProvider


class MailTmAdapterTests(unittest.TestCase):
    @patch("app.email.mailtm.request_json")
    def test_documented_account_token_flow_keeps_password_private(self, request):
        request.side_effect = [
            {"hydra:member": [{"domain": "mail.test"}]},
            {"id": "remote-account"},
            {"token": "private-token"},
        ]
        provider = MailTmProvider()
        inbox = provider.create_inbox()
        self.assertTrue(inbox.address.endswith("@mail.test"))
        self.assertEqual(3, request.call_count)
        account_payload = request.call_args_list[1].kwargs["payload"]
        token_payload = request.call_args_list[2].kwargs["payload"]
        self.assertEqual(account_payload["password"], token_payload["password"])
        self.assertNotIn("password", str(inbox.to_dict()))
        self.assertNotIn("private-token", str(inbox.to_dict()))

    @patch("app.email.mailtm.request_json")
    def test_message_list_and_detail_are_normalized(self, request):
        request.side_effect = [
            {"hydra:member": [{"id": "message-1"}]},
            {
                "id": "message-1",
                "from": {"address": "sender@example.test"},
                "subject": "Test",
                "text": "Your verification code is 123456",
                "createdAt": "2026-01-01T00:00:00Z",
            },
        ]
        provider = MailTmProvider()
        provider._tokens["local-inbox"] = "private-token"
        messages = provider.get_messages("local-inbox")
        self.assertEqual(1, len(messages))
        self.assertEqual("message-1", messages[0].id)
        self.assertEqual("sender@example.test", messages[0].sender)
        self.assertEqual("Bearer private-token", request.call_args_list[0].kwargs["headers"]["Authorization"])

    def test_unknown_local_inbox_does_not_make_network_request(self):
        with patch("app.email.mailtm.request_json") as request:
            with self.assertRaises(KeyError):
                MailTmProvider().get_messages("missing")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
