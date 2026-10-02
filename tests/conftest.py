"""Isolate every test from the user's git configuration."""
import pytest

TEST_GIT_CONFIG = (
    "[user]\n\tname = Test User\n\temail = test@example.com\n"
    "[init]\n\tdefaultBranch = main\n"
    "[commit]\n\tgpgsign = false\n"
    "[tag]\n\tgpgsign = false\n"
)


@pytest.fixture(autouse=True)
def isolated_git_config(tmp_path_factory, monkeypatch):
    """Point git at a throwaway global config and disable the system one."""
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    config.write_text(TEST_GIT_CONFIG, encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
