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
    """Point git at a throwaway global config and disable the system one.

    GIT_CONFIG_GLOBAL does not cover ``$XDG_CONFIG_HOME/git/ignore`` and
    ``git/attributes``, which git reads on its own; an empty XDG directory does.
    """
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    config.write_text(TEST_GIT_CONFIG, encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg")))
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
