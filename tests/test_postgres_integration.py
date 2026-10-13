"""Opt-in real Postgres tests; isolated rows, no production snapshot imports."""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from regintel.infrastructure.postgres_store import PostgresStore


@unittest.skipUnless(os.environ.get("REGINTEL_TEST_DATABASE_URL"), "未設定獨立的資料庫測試連線")
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["REGINTEL_TEST_DATABASE_URL"]
        self.namespace = "test-" + uuid.uuid4().hex
        self.store = PostgresStore(self.dsn, self.namespace)
        self.store.check()

    def tearDown(self):
        # Delete only the random namespace created by this individual test.
        self.assertRegex(self.namespace, r"^test-[a-f0-9]{32}$")
        with self.store.connection() as conn:
            conn.execute("DELETE FROM public.regintel_documents WHERE namespace = %s", (self.namespace,))

    def test_new_application_instance_reads_retained_documents(self):
        self.store.write("history", {"events": [{"title": "官方公告"}]})
        restarted = PostgresStore(self.dsn, self.namespace)
        self.assertEqual(restarted.load("history"), {"events": [{"title": "官方公告"}]})

    def test_failed_transaction_preserves_previous_snapshot(self):
        self.store.write("history", {"before": True})
        with self.assertRaises(ValueError), self.store.transaction("history", "laws"):
            self.store.write("history", {"before": False})
            self.store.write("laws", {"partial": True})
            raise ValueError("abort import")
        self.assertEqual(self.store.load("history"), {"before": True})
        self.assertEqual(self.store.load("laws"), {})

    def test_two_instances_merge_without_lost_updates(self):
        self.store.write("history", {"events": []})

        def append(prefix):
            instance = PostgresStore(self.dsn, self.namespace)
            for index in range(4):
                with instance.transaction("history"):
                    payload = instance.load("history")
                    payload["events"].append(f"{prefix}-{index}")
                    instance.write("history", payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(append, ("a", "b")))
        self.assertEqual(len(set(self.store.load("history")["events"])), 8)

    def test_revision_changes_only_when_contents_change(self):
        self.store.write("laws", {"version": 1})
        before = self.store.revisions(["laws"])["laws"]
        self.store.write("laws", {"version": 1})
        self.assertEqual(self.store.revisions(["laws"])["laws"], before)
        self.store.write("laws", {"version": 2})
        self.assertEqual(self.store.revisions(["laws"])["laws"], before + 1)
