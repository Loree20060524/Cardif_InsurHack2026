"""Storage selection, cloud cache reuse, and preservation of existing records."""

import copy
import importlib.util
import os
import tempfile
import time
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from regintel.application import event_analysis, event_history, refresh, regulatory_qa
from regintel.infrastructure import json_store, postgres_store
from scripts.migrate_storage import import_snapshot, load_environment, load_snapshot


class StorageSettingsTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_local_default_does_not_need_a_database_driver(self):
        self.assertIsNone(postgres_store.get_store())

    def test_marketplace_urls_and_explicit_override_are_supported(self):
        for name in postgres_store.URL_KEYS:
            with self.subTest(name=name), patch.dict(os.environ, {name: "postgresql://example/db"}):
                self.assertEqual(postgres_store.database_settings(), ("postgresql://example/db", "regintel-v1"))
        os.environ.update(DATABASE_URL="postgresql://default/db", REGINTEL_DATABASE_URL="postgresql://override/db")
        self.assertEqual(postgres_store.database_settings()[0], "postgresql://override/db")

    def test_libpq_variables_from_marketplace_enable_postgres(self):
        os.environ.update(PGHOST="example.neon.tech", PGDATABASE="neondb")
        self.assertTrue(postgres_store.configured())

    def test_invalid_connection_never_exposes_value_or_falls_back(self):
        os.environ["DATABASE_URL"] = "invalid://private-password@example/db"
        with self.assertRaises(postgres_store.StorageError) as error:
            postgres_store.get_store()
        self.assertNotIn("private-password", str(error.exception))


class CloudStorageBehaviorTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("psycopg"), "未安裝資料庫驅動")
    def test_driver_connection_error_never_leaks_credentials(self):
        import psycopg
        store = postgres_store.PostgresStore("postgresql://user:private-password@example/db", "test")
        with patch.object(psycopg, "connect", side_effect=psycopg.OperationalError("private-password in driver context")):
            with self.assertRaises(postgres_store.StorageError) as error:
                store.load("history")
        self.assertNotIn("private-password", str(error.exception))

    def test_failed_cloud_read_does_not_return_local_or_empty_history(self):
        store = Mock()
        store.load.side_effect = postgres_store.StorageError("資料庫暫時無法讀寫")
        with patch.object(json_store, "get_store", return_value=store):
            with self.assertRaises(postgres_store.StorageError):
                json_store.load_json_file(Path("history.json"))

    def test_questions_rebuild_index_after_shared_revision_changes(self):
        store = Mock(namespace="test")
        store.revisions.side_effect = [{}, {}, {"regintel_law_versions_v1.json": 2}]
        with patch.object(json_store, "get_store", return_value=store), \
             patch.object(regulatory_qa, "load_json_file", return_value={}), \
             patch.object(regulatory_qa, "_index", None), \
             patch.object(regulatory_qa, "_index_signature", None), \
             patch.object(regulatory_qa, "KnowledgeIndex", side_effect=[Mock(), Mock()]) as build:
            first = regulatory_qa.knowledge_index()
            self.assertIs(first, regulatory_qa.knowledge_index())
            self.assertIsNot(first, regulatory_qa.knowledge_index())
            self.assertEqual(build.call_count, 2)

    def test_cold_instance_reuses_saved_events_without_network(self):
        saved = {"timestamp": time.time(), "events": [{"id": "retained"}], "sources": {}}
        with patch.object(refresh, "configured", return_value=True), \
             patch.object(refresh, "document_transaction", side_effect=lambda *a, **k: nullcontext()), \
             patch.object(refresh, "load_json_file", return_value=saved), \
             patch.object(refresh, "_mem_cache", {"timestamp": 0, "events": []}), \
             patch.object(refresh, "_last_manual_refresh_ts", 0), \
             patch.object(refresh, "fetch_url") as fetch:
            self.assertEqual(refresh.refresh_data()["events"], saved["events"])
            fetch.assert_not_called()

    def test_another_refresh_returns_saved_events_while_writer_is_busy(self):
        saved = {"timestamp": 0, "events": [{"id": "retained"}], "sources": {}}
        with patch.object(refresh, "_refresh_data", side_effect=postgres_store.StorageBusyError()), \
             patch.object(refresh, "load_json_file", return_value=saved):
            result = refresh.refresh_data(True)
        self.assertEqual(result["events"], saved["events"])
        self.assertTrue(result["refresh_in_progress"])
        self.assertTrue(result["manual_refresh_limited"])

    def test_history_invalidation_reaches_other_cloud_instances(self):
        saved = {"timestamp": 42, "events": [{"id": "retained"}]}
        with patch.object(refresh, "configured", return_value=True), \
             patch.object(refresh, "document_transaction", side_effect=lambda *a, **k: nullcontext()), \
             patch.object(refresh, "_mem_cache", {}), \
             patch.object(refresh, "load_json_file", return_value=saved), \
             patch.object(refresh, "atomic_write_json") as write:
            refresh.invalidate_refresh_cache()
        self.assertEqual(write.call_args.args[1]["timestamp"], 0)
        self.assertEqual(write.call_args.args[1]["events"], [{"id": "retained"}])

    def test_slow_archive_response_does_not_reset_shared_page_cursor(self):
        empty = {"events": [], "sources": {}}
        advanced = {"events": [], "sources": {"reg_news": {"loaded_pages": 2, "has_more": False}}}
        record = {"id": "news", "source_key": "reg_news", "title": "公告", "url": "https://www.fsc.gov.tw/", "category": "監理新聞"}
        with patch.object(event_history, "load_json_file", side_effect=[empty, advanced]), \
             patch.object(event_history, "robots_allowed", return_value=True), \
             patch.object(event_history, "fetch_url", return_value=(200, "頁數 1 / 2".encode(), "text/html", {})), \
             patch.object(event_history, "parse_announcement_html", return_value=[record]), \
             patch.object(event_history, "atomic_write_json") as save:
            event_history.load_older_events(["reg_news"])
        self.assertEqual(save.call_args.args[1]["sources"]["reg_news"], {"loaded_pages": 2, "has_more": False})

    def test_analysis_merges_into_latest_cache_after_slow_generation(self):
        event = {"id": "analysis", "source_key": "reg_news", "title": "保險業風險管理公告",
                 "description": "保險業辦理投資作業應依規定建立內部控制制度，保存投資評估、核准及覆核紀錄，並定期檢查風險限額。"}
        stale = {"analyses": {}, "management": {}}
        latest = {"analyses": {"teammate": {"summary": "隊友的分析"}},
                  "management": {"report": {"summary": "隊友的管理摘要"}}}
        with patch.object(event_analysis, "load_ai_cache", side_effect=[stale, latest]), \
             patch.object(event_analysis, "get_law_comparisons", return_value=[]), \
             patch.object(event_analysis, "call_ollama_structured_json", return_value={}), \
             patch.object(event_analysis, "sanitize_ai_analysis", return_value={"analysis_mode": "AI 深度分析"}), \
             patch.object(event_analysis, "document_transaction", side_effect=lambda *a: nullcontext()), \
             patch.object(event_analysis, "atomic_write_json") as save:
            event_analysis.analyze_event_with_ai(event)
        payload = save.call_args.args[1]
        self.assertIn("teammate", payload["analyses"])
        self.assertIn("report", payload["management"])
        self.assertEqual(len(payload["analyses"]), 2)


class SnapshotStore:
    """In-memory document contract for testing migration's preservation policy."""
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(documents or {})
        self.writes = 0

    @contextmanager
    def transaction(self, **kwargs):
        backup = copy.deepcopy(self.documents)
        try:
            yield
        except Exception:
            self.documents = backup
            raise

    def load(self, key):
        return copy.deepcopy(self.documents.get(key, {}))

    def revisions(self, keys):
        return {key: 1 for key in keys if key in self.documents}

    def write(self, key, payload):
        self.documents[key] = copy.deepcopy(payload)
        self.writes += 1


class MigrationTests(unittest.TestCase):
    def test_empty_import_verifies_data_and_identical_rerun_is_safe(self):
        store = SnapshotStore()
        documents = {"history": {"events": ["公告"]}, "laws": {"laws": {"法規": ["版本"]}}}
        self.assertTrue(import_snapshot(store, documents))
        self.assertEqual(store.documents, documents)
        self.assertFalse(import_snapshot(store, documents))
        self.assertEqual(store.writes, 2)

    def test_existing_or_partial_cloud_data_is_never_overwritten(self):
        store = SnapshotStore({"history": {"events": ["雲端新資料"]}})
        with self.assertRaises(ValueError):
            import_snapshot(store, {"history": {"events": ["本機舊資料"]}, "laws": {}})
        self.assertEqual(store.documents["history"]["events"], ["雲端新資料"])
        self.assertEqual(store.writes, 0)

    def test_invalid_or_missing_local_document_aborts_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_snapshot(Path(directory))

    def test_secret_file_values_are_loaded_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "database.env"
            path.write_text('REGINTEL_DATABASE_URL="postgresql://user:$(secret)@example/db"\n', encoding="utf-8")
            load_environment(path)
            self.assertIn("$(secret)", os.environ["REGINTEL_DATABASE_URL"])
