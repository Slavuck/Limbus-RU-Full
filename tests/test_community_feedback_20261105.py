"""Regressions for community reports and the related effect-display audit."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RU = ROOT / 'Localize/Limbus-RU-Full'
if not RU.is_dir():
    RU = ROOT / 'output/Limbus-RU-Full'


def records(file):
    return {row['id']: row for row in json.loads((RU / file).read_text('utf-8-sig'))['dataList']}


class CommunityFeedbackTests(unittest.TestCase):
    def test_support_passives_and_faction_filters(self):
        self.assertIn('1 Повышение дробящего урона', records('Passives.json')[1030621]['desc'])
        self.assertIn(' повышает счётчик ', records('Passives_check4.json')[1040531]['desc'])
        self.assertIn('Подзаряда', records('Passives_Abnormality.json')[804501]['desc'])
        self.assertIn('Подзаряд', records('BattleKeywords.json')['SelfCharge']['desc'])
        filters = records('FormationNameEtcFilter.json')
        self.assertEqual(filters['formation_name_filter_Etc_RING_FINGER']['content'], 'Безымянный палец')
        self.assertEqual(filters['formation_name_filter_Etc_SHI']['content'], 'Си')

    def test_lamp_and_dazzle_mechanics_in_both_effect_tables(self):
        for file in ('BattleKeywords.json', 'Bufs.json'):
            effects = records(file)
            lamp = effects['LanternGregBigBird']['desc']
            self.assertIn('Наносит 3 Ослепления', lamp)
            self.assertIn('наибольшими текущими ОЗ', lamp)
            dazz = effects['DelusionGregBigBird']['desc']
            self.assertIn('0,5%', dazz)
            self.assertNotIn('округляется вниз', dazz)
            self.assertIn('чей тип паники нельзя изменить', dazz)
            self.assertIn('2 Понижения уровня атаки', dazz)
            self.assertIn('4 Понижения уровня атаки', dazz)

    def test_no_stray_reference_tails(self):
        pattern = re.compile(r'\(;[A-Za-z0-9_]+\)')
        bad = []
        for path in RU.rglob('*.json'):
            if pattern.search(path.read_text('utf-8-sig')):
                bad.append(str(path.relative_to(RU)))
        self.assertEqual(bad, [])

    def test_prescript_redirect_and_damage_targets(self):
        desc = records('Passives_Abnormality_Refraction6.json')[955103]['desc']
        self.assertIn('оставшиеся навыки против случайного Грешника', desc)
        self.assertIn('его ОЗ опускаются до 1', desc)
        self.assertIn('на 30% больше урона всем целям', desc)


if __name__ == '__main__':
    unittest.main()
