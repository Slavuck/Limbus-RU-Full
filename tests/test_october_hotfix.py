"""Regressions the structural audit alone cannot detect (wrong passive/lore)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALIZE = ROOT / 'Localize/Limbus-RU-Full'
if not LOCALIZE.is_dir():
    LOCALIZE = ROOT / 'output/Limbus-RU-Full'


def records(name, key='id'):
    return {r[key]: r for r in json.loads((LOCALIZE / name).read_text('utf-8-sig'))['dataList']}


class OctoberHotfixTests(unittest.TestCase):
    def test_boss_win_condition_only_in_the_correct_passive(self):
        data = records('Passives_Abnormality-a1c10p3.json')
        self.assertIn('[BuffetDream]', data[151703]['desc'])
        self.assertIn('[BuffetScruple]', data[151703]['desc'])
        self.assertNotIn('[BuffetDream]', data[151709]['desc'])
        self.assertNotIn('завершает сражение', data[151709]['desc'])

    def test_scarf_has_both_gameplay_effects_in_stat_text(self):
        item = records('RPGSystem/rpg-loc-item-common-a1c10p3.json', 'key')['I990931']
        self.assertIn('+350', item['statText'])
        self.assertIn('ниже 1', item['statText'])
        self.assertNotIn('+350', item['description'])

    def test_deleted_story_reference_is_not_in_the_subtitle(self):
        line = records('StoryData/S1031B.json')[10]['content']
        self.assertIn('Мерсо', line)
        self.assertNotIn('Кромер', line)


if __name__ == '__main__':
    unittest.main()
