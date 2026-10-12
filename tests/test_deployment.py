"""Exercise independent cloud configuration and persistence across process restarts."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from regintel import web

ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def run_python(self, source, **settings):
        environment = dict(os.environ)
        for name in ("REGINTEL_HOST", "REGINTEL_DATA_DIR", "PORT", "VERCEL"):
            environment.pop(name, None)
        environment.update(settings)
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", source], cwd=ROOT, env=environment,
            capture_output=True, text=True, encoding="utf-8", check=True, timeout=15,
        )
        return json.loads(result.stdout)

    def test_local_defaults_preserve_existing_data_location(self):
        result = self.run_python('''
import json
from regintel import config
print(json.dumps({"host": config.HOST, "port": config.PORT,
    "paths": [str(getattr(config, name).parent) for name in
    ("CACHE_FILE", "SOURCE_STORE_FILE", "AI_CACHE_FILE", "EVENT_HISTORY_FILE", "LAW_VERSIONS_FILE")]}))
''')
        self.assertEqual(result["host"], "127.0.0.1")
        self.assertEqual(result["port"], 8082)
        self.assertEqual(result["paths"], [str(ROOT)] * 5)

    def test_vercel_uses_writable_temporary_storage_until_database_is_connected(self):
        result = self.run_python('''
import json
import tempfile
from pathlib import Path
from regintel import config
print(json.dumps({"vercel": config.IS_VERCEL, "directory": str(config.DATA_DIR),
    "temporary": str(Path(tempfile.gettempdir()) / "regintel")}))
''', VERCEL="1")
        self.assertTrue(result["vercel"])
        self.assertEqual(result["directory"], result["temporary"])
        self.assertNotEqual(result["directory"], str(ROOT))

    def test_cloud_data_survives_a_new_application_process(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = str(Path(folder) / "volume" / "regintel")
            settings = {"REGINTEL_HOST": "0.0.0.0", "PORT": "10000", "REGINTEL_DATA_DIR": directory}
            written = self.run_python('''
import json
from regintel import config
from regintel.infrastructure.json_store import atomic_write_json
names = ("CACHE_FILE", "SOURCE_STORE_FILE", "AI_CACHE_FILE", "EVENT_HISTORY_FILE", "LAW_VERSIONS_FILE")
for name in names:
    atomic_write_json(getattr(config, name), {"retained": name})
print(json.dumps({"host": config.HOST, "port": config.PORT,
    "paths": [str(getattr(config, name).parent) for name in names]}))
''', **settings)
            self.assertEqual(written["host"], "0.0.0.0")
            self.assertEqual(written["port"], 10000)
            self.assertEqual(written["paths"], [directory] * 5)
            read = self.run_python('''
import json
from regintel import config
from regintel.infrastructure.json_store import load_json_file
names = ("CACHE_FILE", "SOURCE_STORE_FILE", "AI_CACHE_FILE", "EVENT_HISTORY_FILE", "LAW_VERSIONS_FILE")
print(json.dumps({name: load_json_file(getattr(config, name))["retained"] for name in names}))
''', **settings)
            self.assertTrue(all(name == value for name, value in read.items()))
            self.assertEqual(len(read), 5)

    def test_server_honors_host_and_platform_port(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(web, "HOST", "0.0.0.0"), patch.object(web, "PORT", 10000), \
             patch.object(web, "DATA_DIR", Path(folder) / "volume"), \
             patch.object(web, "RegIntelHTTPServer") as server, \
             patch.object(web, "probe_ollama", return_value={"reachable": False}), \
             patch("builtins.print"):
            self.assertEqual(web.main(), 0)
            server.assert_called_once_with(("0.0.0.0", 10000), web.Handler)
            server.return_value.serve_forever.assert_called_once()
            server.return_value.server_close.assert_called_once()
            self.assertTrue(web.DATA_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
