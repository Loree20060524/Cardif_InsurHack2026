"""Keep local inference on Ollama unless a cloud provider is selected explicitly."""

import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


CONFIG_PATH = Path(__file__).resolve().parents[1] / "regintel" / "config.py"


class AIProviderConfigTests(unittest.TestCase):
    def load_config(self, environment, local_env=""):
        clean_environment = {
            name: value for name, value in os.environ.items()
            if not name.startswith(("AI_", "GROQ_", "OLLAMA_", "VERCEL"))
        }
        clean_environment.update(environment)
        with (
            patch.dict(os.environ, clean_environment, clear=True),
            patch.object(Path, "is_file", lambda path: path.name == ".env.local"),
            patch.object(Path, "read_text", return_value=local_env),
            patch.object(Path, "mkdir"),
        ):
            return runpy.run_path(str(CONFIG_PATH))

    def test_local_default_is_ollama(self):
        config = self.load_config({})
        self.assertEqual(config["AI_PROVIDER"], "ollama")
        self.assertEqual(config["AI_MODEL"], "qwen3:4b")

    def test_local_key_alone_does_not_select_cloud(self):
        for environment, local_env in (
            ({"GROQ_API_KEY": "test-key"}, ""),
            ({}, "GROQ_API_KEY=test-key\n"),
        ):
            with self.subTest(source="environment" if environment else "local file"):
                config = self.load_config(environment, local_env)
                self.assertEqual(config["AI_PROVIDER"], "ollama")
                self.assertEqual(config["AI_MODEL"], "qwen3:4b")

    def test_local_cloud_provider_can_be_selected_explicitly(self):
        config = self.load_config({}, "AI_PROVIDER=groq\nGROQ_API_KEY=test-key\n")
        self.assertEqual(config["AI_PROVIDER"], "groq")
        self.assertEqual(config["AI_MODEL"], "openai/gpt-oss-120b")

    def test_shell_provider_overrides_local_file(self):
        config = self.load_config({"AI_PROVIDER": "ollama"}, "AI_PROVIDER=groq\nGROQ_API_KEY=test-key\n")
        self.assertEqual(config["AI_PROVIDER"], "ollama")

    def test_vercel_uses_cloud_and_ignores_local_file(self):
        config = self.load_config({"VERCEL": "1", "GROQ_API_KEY": "test-key"}, "AI_PROVIDER=ollama\n")
        self.assertEqual(config["AI_PROVIDER"], "groq")
        self.assertEqual(config["AI_MODEL"], "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()
