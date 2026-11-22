"""Check the hook configuration files of every host."""

import json
import shlex
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Antigravity, Claude Code, and Codex hook configuration files.
HOOK_FILES = (
    ROOT / "hooks.json",
    ROOT / "hooks" / "hooks.json",
    ROOT / "hooks" / "hooks.codex.json",
)
# The flags that make system_notification.py play a sound.
SOUND_FLAGS = {"--success", "--error", "--info", "--attention"}


def configured_commands(path):
    """Return every hook command in one hook configuration file.

    The Antigravity file nests events under "core-hooks", and its Stop
    entry is itself a hook. The other files nest events under "hooks".
    """
    config = json.loads(path.read_text())
    events = config["core-hooks"] if "core-hooks" in config else config["hooks"]
    return [
        hook["command"]
        for entries in events.values()
        for entry in entries
        for hook in entry.get("hooks", [entry])
    ]


class HookConfigTests(unittest.TestCase):
    def test_notification_commands_pass_one_sound_flag(self):
        checked = 0
        for path in HOOK_FILES:
            for command in configured_commands(path):
                if "system_notification.py" not in command:
                    continue
                checked += 1
                with self.subTest(file=path.relative_to(ROOT), command=command):
                    flags = [
                        token for token in shlex.split(command)
                        if token in SOUND_FLAGS
                    ]
                    self.assertEqual(len(flags), 1, flags)
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
