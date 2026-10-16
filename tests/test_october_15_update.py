"""Gameplay corrections that placeholder and structure checks cannot verify."""
import json
import unittest
from pathlib import Path

LOCALIZE = Path(__file__).resolve().parents[1] / 'Localize/Limbus-RU-Full'
def records(name):
    return {r['id']:r for r in json.loads((LOCALIZE/name).read_text('utf-8-sig'))['dataList']}

class October15UpdateTests(unittest.TestCase):
    def test_blue_starshard_defense_down_applies_next_turn_at_every_upgrade(self):
        data=records('EGOgift_MirrorDungeon-mowe-re.json')
        for key in (9817,19817,29817):
            self.assertIn('[DefenseDown]',data[key]['desc'])
            self.assertIn('на следующий ход',data[key]['desc'])

    def test_searing_brass_requires_burn_activation_at_every_upgrade(self):
        data=records('EGOgift_TwiningThreads.json')
        for key in (9267,19267,29267):
            self.assertIn('из-за срабатывания [Combustion]',data[key]['desc'])

    def test_new_sinclair_skill_does_not_claim_unconditional_transformation(self):
        text=json.dumps(records('Passives.json')[1101603],ensure_ascii=False)
        self.assertIn('150 [HungrySinclair]',text)
        self.assertIn('100+ [HungrySinclair]',text)
        self.assertIn('впервые в этом бою',text)

if __name__=='__main__':unittest.main()
