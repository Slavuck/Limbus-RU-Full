"""Verify combat mechanics and identity migrations beyond format checks."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALIZE = ROOT / 'Localize/Limbus-RU-Full'

def records(name, key='id'):
    return {r[key]: r for r in json.loads((LOCALIZE/name).read_text('utf-8-sig'))['dataList']}


class October8UpdateTests(unittest.TestCase):
    def test_boss_tips_follow_new_ids_and_do_not_warn_about_removed_penalty(self):
        tips = records('BattleResultHint-a1c10p3.json')
        self.assertFalse(set(tips) & {f'battleTip_11036_{i}' for i in range(1, 5)})
        self.assertEqual(sum(k.startswith('battleTip_11036_phase') for k in tips), 7)
        self.assertNotIn('получает больше', tips['battleTip_11041_2']['content'])
        self.assertIn('Священник', tips['battleTip_11036_phase3_2']['content'])

    def test_scarf_choices_and_dialogue_are_present(self):
        choices = records('RPGSystem/rpg-loc-dialogue-choice-route-c.json', 'key')
        self.assertEqual(choices['DCRSCW02_C1']['text'], 'Продолжить попытки.')
        dialogue = records('RPGSystem/rpg-loc-dialogue-route-c.json', 'key')
        self.assertEqual(len(dialogue['DRSCW01_C1']['texts']), 3)
        self.assertIn('Мерсо', dialogue['DRSCW02_C1']['texts'][1]['text'])

    def test_la_moisson_does_not_prematurely_claim_october_15_limit(self):
        text = records('Passives_Abnormality-a1c10p3.json')[151706]['desc']
        self.assertIn('Ла Деманд', text)
        self.assertNotIn('раз за ход', text)
        self.assertNotIn('раза за ход', text)

    def test_decision_and_pwie_restore_sanity_without_old_damage_penalty(self):
        for filename in ('Bufs-a1c10p3.json', 'BattleKeywords-a1c10p3.json'):
            data = records(filename)
            self.assertIn('15 СД', data['BuffetResolve']['desc'])
            self.assertNotIn('получаемый', data['BuffetResolve']['desc'])
            self.assertIn('-75%', data['BuffetScruple']['desc'])
            self.assertIn('15 СД', data['BuffetScruple']['desc'])

    def test_lacan_skill_penalties_and_clash_conditions_are_current(self):
        data = records('Skills_Abnormality-a1c10p3.json')
        self.assertIn('-95%', data[151709]['levelList'][0]['desc'])
        self.assertIn('независимо от скорости', data[151713]['levelList'][0]['desc'])
        self.assertNotIn('Нельзя ошеломить', data[151713]['levelList'][0]['desc'])


if __name__ == '__main__':
    unittest.main()
