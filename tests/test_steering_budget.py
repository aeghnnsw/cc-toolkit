"""Root CLAUDE.md keeps its word budget and its sections, and the retrospective proposes a check first (#467).

Retrospectives grew CLAUDE.md from 510 to 994 words with prose rules and no check (#390, #392). A
retrospective now proposes a check, a script, or a test before a prose rule; see docs/agents/retro.md
step 4. The budget counts words as `wc -w` does: each run of characters between spaces.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import FENCE, ROOT

CLAUDE = ROOT / 'CLAUDE.md'
RETRO = ROOT / 'docs' / 'agents' / 'retro.md'
WORD_BUDGET = 450
HEADINGS = (
    '# cc-toolkit', '## Agent skills', '### Coding standards', '### Issue tracker', '### Triage labels',
    '### Domain docs', '### Navigation retrospectives', '## Development workflow', '## Plugin changes',
    '## Automation',
)
ADVICE = ('Propose a check, a script, or a test before a prose rule (docs/agents/retro.md step 4), '
          'or move detail to CONTRIBUTING.md or docs/agents/ and leave a pointer.')


class SteeringBudgetTest(unittest.TestCase):
    def test_claude_md_fits_its_word_budget(self):
        words = len(CLAUDE.read_text(encoding='utf-8').split())
        self.assertLessEqual(words, WORD_BUDGET, f'CLAUDE.md has {words} words; its budget is {WORD_BUDGET}. {ADVICE}')

    def test_claude_md_adds_no_section(self):
        text = FENCE.sub('', CLAUDE.read_text(encoding='utf-8'))
        added = [line for line in re.findall(r'(?m)^#{1,6} .*$', text) if line not in HEADINGS]
        self.assertEqual(added, [], f'CLAUDE.md adds sections. {ADVICE}')

    def test_the_retrospective_proposes_a_check_first_and_changes_no_tracked_file(self):
        steps = ' '.join(RETRO.read_text(encoding='utf-8').split())
        self.assertIn('Propose a check, a script, or a test first. Propose new text in a steering file only '
                      'when no check, script, or test can work, and give the reason in the issue.', steps)
        self.assertIn('git rev-parse HEAD git diff HEAD --binary | git hash-object --stdin', steps)
        self.assertIn('7. Run the two commands from before step 1 again. They must print the same two lines.',
                      steps)
        self.assertNotIn('Prefer a tool fix or an automated check', steps)


if __name__ == '__main__':
    unittest.main()
