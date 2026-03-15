import importlib


def test_live_env_loader_keeps_azure_openai_pair_from_dotenv(monkeypatch, tmp_path):
    live_module = importlib.import_module("tests.test_live_azure_backends")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").write_text(
        "\n".join(
            [
                "AZURE_OPENAI_ENDPOINT=https://dotenv.openai.azure.com/",
                "AZURE_OPENAI_API_KEY=dotenv-key",
                "AZURE_OPENAI_API_VERSION=2025-04-01-preview",
            ]
        ),
        encoding="utf-8",
    )
    azd_dir = repo_root / ".azure" / "agent-memory"
    azd_dir.mkdir(parents=True)
    (azd_dir / ".env").write_text(
        "\n".join(
            [
                "AZURE_OPENAI_ENDPOINT=https://azd.openai.azure.com/",
                "AZURE_OPENAI_API_KEY=azd-key",
                "AZURE_AI_SEARCH_ENDPOINT=https://search.azure.com/",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(live_module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(live_module, "_azd_env_value", lambda name: None)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_SEARCH_ENDPOINT", raising=False)

    env = live_module._load_live_env()

    assert env["AZURE_OPENAI_ENDPOINT"] == "https://dotenv.openai.azure.com/"
    assert env["AZURE_OPENAI_API_KEY"] == "dotenv-key"
    assert env["AZURE_AI_SEARCH_ENDPOINT"] == "https://search.azure.com/"


def test_live_env_loader_allows_process_env_override(monkeypatch, tmp_path):
    live_module = importlib.import_module("tests.test_live_azure_backends")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").write_text("AZURE_OPENAI_ENDPOINT=https://dotenv.openai.azure.com/\n", encoding="utf-8")
    azd_dir = repo_root / ".azure" / "agent-memory"
    azd_dir.mkdir(parents=True)
    (azd_dir / ".env").write_text("AZURE_AI_SEARCH_ENDPOINT=https://azd-search.azure.com/\n", encoding="utf-8")

    monkeypatch.setattr(live_module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(live_module, "_azd_env_value", lambda name: None)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://process.openai.azure.com/")
    monkeypatch.setenv("AZURE_AI_SEARCH_ENDPOINT", "https://process-search.azure.com/")

    env = live_module._load_live_env()

    assert env["AZURE_OPENAI_ENDPOINT"] == "https://process.openai.azure.com/"
    assert env["AZURE_AI_SEARCH_ENDPOINT"] == "https://process-search.azure.com/"
