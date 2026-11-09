import tempfile
import unittest
from dataclasses import replace

from app.chat import ChatService
from app.database import Database
from app.memory import MemoryExtractor, MemoryStore
from app.providers.base import ProviderError

from tests.helpers import test_settings


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = test_settings(self.temp.name)
        self.database = Database(self.settings.database_path)
        self.store = MemoryStore(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def test_conversation_and_messages_survive_reopen(self):
        conversation = self.store.create_conversation()
        self.store.add_message(conversation["id"], "user", "Hello persistent world")
        self.store.add_message(conversation["id"], "assistant", "Hello!", "mock")

        reopened = MemoryStore(Database(self.settings.database_path))
        loaded = reopened.get_conversation(conversation["id"])
        self.assertEqual("Hello persistent world", loaded["title"])
        self.assertEqual(["user", "assistant"], [message["role"] for message in loaded["messages"]])
        self.assertEqual(2, reopened.list_conversations()[0]["message_count"])

    def test_conversation_rename_delete_and_cascade(self):
        conversation = self.store.create_conversation("Original")
        message = self.store.add_message(conversation["id"], "user", "Hello")
        memory = self.store.add_memory(
            "A sourced fact",
            source_conversation_id=conversation["id"],
            source_message_id=message["id"],
        )
        renamed = self.store.rename_conversation(conversation["id"], "Renamed")
        self.assertEqual("Renamed", renamed["title"])
        self.assertEqual({"conversations": 1, "messages": 1, "memories": 1}, self.store.stats())
        self.assertTrue(self.store.delete_conversation(conversation["id"]))
        self.assertIsNone(self.store.get_conversation(conversation["id"]))
        remaining = self.store.search("sourced")[0]
        self.assertEqual(memory["id"], remaining["id"])
        self.assertIsNone(remaining["source_conversation_id"])
        self.assertIsNone(remaining["source_message_id"])
        self.assertFalse(self.store.delete_conversation(conversation["id"]))

    def test_memory_search_ranks_relevant_fact(self):
        self.store.add_memory("My favorite language is Python", ["profile"])
        self.store.add_memory("I plan to study databases on Friday", ["schedule"])
        results = self.store.search("What is my favorite language?")
        self.assertEqual("My favorite language is Python", results[0]["content"])
        self.assertGreater(results[0]["score"], 0)

    def test_blank_search_returns_recent_memories(self):
        self.store.add_memory("first")
        self.store.add_memory("second", ["One", "one", "Two"])
        results = self.store.search()
        self.assertEqual(2, len(results))
        self.assertEqual(["one", "two"], results[0]["tags"])

    def test_memory_can_be_deleted(self):
        memory = self.store.add_memory("temporary")
        self.assertTrue(self.store.delete_memory(memory["id"]))
        self.assertFalse(self.store.delete_memory(memory["id"]))
        self.assertEqual([], self.store.search())

    def test_invalid_messages_are_rejected(self):
        conversation = self.store.create_conversation()
        with self.assertRaises(ValueError):
            self.store.add_message(conversation["id"], "system", "not allowed")
        with self.assertRaises(ValueError):
            self.store.add_message(conversation["id"], "user", "   ")
        with self.assertRaises(KeyError):
            self.store.add_message("missing", "user", "hello")

    def test_extractor_saves_explicit_facts_but_not_credentials(self):
        conversation = self.store.create_conversation()
        self.store.add_message(conversation["id"], "user", "Remember that I study on weekdays. My favorite editor is Termux.")
        self.store.add_message(conversation["id"], "user", "Remember that my password is never-store-this")
        self.store.add_message(conversation["id"], "assistant", "Remember that this assistant text is ignored")
        extracted = MemoryExtractor().extract(self.store, conversation["id"])
        self.assertEqual(2, len(extracted))
        self.assertFalse(any("never-store-this" in item["content"] for item in extracted))
        self.assertEqual([], MemoryExtractor().extract(self.store, conversation["id"]))


class ChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = test_settings(self.temp.name)
        self.store = MemoryStore(Database(self.settings.database_path))
        self.chat = ChatService(self.store, self.settings)

    def tearDown(self):
        self.temp.cleanup()

    def test_mock_chat_persists_turn_and_retrieves_memory(self):
        conversation = self.store.create_conversation()
        self.store.add_memory("My favorite language is Python")
        result = self.chat.send(conversation["id"], "What is my favorite language?")
        self.assertEqual("mock-1", result["model"])
        self.assertIn("Python", result["assistant_message"]["content"])
        self.assertEqual(1, len(result["retrieved_memories"]))
        self.assertEqual(2, len(self.store.get_conversation(conversation["id"])["messages"]))

    def test_chat_reports_and_persists_bounded_context_metadata(self):
        settings = replace(self.settings, history_limit=2, retrieval_limit=1)
        chat = ChatService(self.store, settings)
        conversation = self.store.create_conversation()
        self.store.add_memory("My favorite language is Python")
        for index in range(3):
            self.store.add_message(conversation["id"], "user", f"Earlier message {index}")

        result = chat.send(conversation["id"], "What is my favorite language?")
        context = result["context"]
        self.assertEqual(2, context["history_limit"])
        self.assertEqual(2, context["history_messages"])
        self.assertTrue(context["history_truncated"])
        self.assertEqual(1, context["retrieved_memories"])
        assistant = result["assistant_message"]
        self.assertEqual(2, assistant["context_messages"])
        self.assertTrue(assistant["context_truncated"])
        self.assertEqual(1, assistant["retrieved_memory_count"])
        stored = self.store.get_conversation(conversation["id"])["messages"][-1]
        self.assertTrue(stored["context_truncated"])
        self.assertEqual(2, stored["context_messages"])

    def test_missing_conversation_is_not_created_implicitly(self):
        with self.assertRaises(KeyError):
            self.chat.send("missing", "hello")

    def test_unconfigured_provider_fails_before_saving_partial_turn(self):
        conversation = self.store.create_conversation()
        with self.assertRaises(ProviderError):
            self.chat.send(conversation["id"], "hello", "openai")
        self.assertEqual([], self.store.get_conversation(conversation["id"])["messages"])


if __name__ == "__main__":
    unittest.main()
