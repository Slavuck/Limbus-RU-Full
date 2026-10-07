"""Regression for the user-reported missing Dante reply."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALIZE = ROOT / 'Localize/Limbus-RU-Full'
if not LOCALIZE.is_dir():
    LOCALIZE = ROOT / 'output/Limbus-RU-Full'


class ShortDialogueReleaseTests(unittest.TestCase):
    def test_dante_reply_is_russian_and_has_speech_brackets(self):
        doc = json.loads((LOCALIZE / 'StoryData/S1031B.json').read_text('utf-8-sig'))
        line = next(r for r in doc['dataList'] if r['id'] == 104)['content']
        self.assertIn('Нет', line)
        self.assertNotIn('No', line)
        self.assertTrue(line.startswith('‹') and line.endswith('›'))


if __name__ == '__main__':
    unittest.main()
