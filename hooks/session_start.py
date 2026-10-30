#!/usr/bin/env python3
"""SessionStart hook of the pragmatic-engineering plugin.

1. Copies rules.md from the plugin root to the plugin data folder when it is
   missing or changed. The data folder survives plugin updates and the root
   does not, so the user's ~/.claude/CLAUDE.md imports the copy.
2. Checks that ~/.claude/CLAUDE.md carries the import of the copy and the
   safety line; for each missing one it prints the exact line to add.

It never blocks and never fails a session start: any problem becomes a
notice. Output goes to the session context (additionalContext) and to
the user (systemMessage), with the same text.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RULES_NAME = "rules.md"
SAFETY_LINE = (
    "If the pragmatic-engineering rules (marker PE-RULES v1) or its skills are missing from this "
    "session, tell the user before doing any work: the plugin is uninstalled or disabled."
)


def sync_rules(root: Path, data: Path) -> bool:
    """Copy root/rules.md over data/rules.md when missing or different; True when written."""
    content = (root / RULES_NAME).read_bytes()
    target = data / RULES_NAME
    if target.is_file() and target.read_bytes() == content:
        return False
    data.mkdir(parents=True, exist_ok=True)
    # Write beside the target, then rename: a crash never leaves a truncated copy that CLAUDE.md imports.
    partial = data / (RULES_NAME + ".partial")
    partial.write_bytes(content)
    os.replace(str(partial), str(target))
    return True


def _escape_spaces(path: str) -> str:
    """CLAUDE.md ends an import path at the first space unless a backslash comes before it."""
    return path.replace(" ", "\\ ")


def import_line(data_rules_path: Path, home: Path) -> str:
    """The @-import for the copy, with ~/ when it lives under the home folder."""
    try:
        return "@~/" + _escape_spaces(data_rules_path.relative_to(home).as_posix())
    except ValueError:
        return "@" + _escape_spaces(data_rules_path.as_posix())


def import_lines(data_rules_path: Path, home: Path) -> List[str]:
    """Lines that ~/.claude/CLAUDE.md still needs: the import, then the safety line.

    A missing file needs both. A file that cannot be read raises, so that the
    caller names the real problem instead of calling the lines missing. Bytes
    that are not valid UTF-8 are replaced, so they matter only inside one of
    the two lines. A hard-wrapped safety line still counts: line breaks read
    as spaces.
    """
    try:
        text = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        text = ""
    wanted = import_line(data_rules_path, home)
    accepted = (wanted, "@" + _escape_spaces(data_rules_path.as_posix()))
    missing = []
    if not any(token in text for token in accepted):
        missing.append(wanted)
    if SAFETY_LINE not in " ".join(text.split()):
        missing.append(SAFETY_LINE)
    return missing


def _output(text: str) -> Dict[str, Any]:
    """The hook answer: one text, for Claude (additionalContext) and for the user (systemMessage)."""
    return {
        "systemMessage": text,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
    }


def build_output(updated: bool, missing: List[str]) -> Optional[Dict[str, Any]]:
    """The answer for a finished check, or None when the rules are in place and nothing changed."""
    notes = []
    if updated:
        notes.append(
            "pragmatic-engineering: the rules file was updated; the updated rules apply from the next session."
        )
    if missing:
        notes.append(
            "pragmatic-engineering: ~/.claude/CLAUDE.md does not carry these lines yet; the user adds them "
            "after a dated backup of the file and a diff:\n" + "\n".join(missing)
        )
    if not notes:
        return None
    return _output("\n\n".join(notes))


def _notice(text: str) -> Dict[str, Any]:
    """The answer for a problem that stopped the check: the hook names it instead of failing."""
    return _output("pragmatic-engineering: " + text)


def main() -> int:
    """Run the check for any session start and report; the exit status is always 0."""
    try:
        root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
        data_value = os.environ.get("CLAUDE_PLUGIN_DATA")
        if not data_value:
            output: Optional[Dict[str, Any]] = _notice(
                "the plugin data folder is unknown (CLAUDE_PLUGIN_DATA is not set), so the rules file "
                "was not copied; the rules reach this session only if ~/.claude/CLAUDE.md already imports them."
            )
        else:
            data = Path(data_value)
            updated = sync_rules(root, data)
            output = build_output(updated, import_lines(data / RULES_NAME, Path.home()))
    except Exception as exc:  # taste-exempt: a session start must never fail because of this hook
        output = _notice("the rules check failed (%s: %s)." % (exc.__class__.__name__, exc))
    if output:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
