import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from audit_community_feedback import scan


RU = ROOT / 'Localize/Limbus-RU-Full'


def records(relative):
    data = json.loads((RU / relative).read_text(encoding='utf-8-sig'))
    return {row['id']: row for row in data['dataList']}


class CommunityHotfixTests(unittest.TestCase):
    def test_reported_story_fields(self):
        self.assertIn('Госпожа Отис', records('StoryData/E402A.json')[24]['content'])
        self.assertIn('упования на приключение', records('StoryData/E042X.json')[8]['content'])
        self.assertIn('получила, что хотела', records('StoryData/S514B.json')[106]['content'])
        self.assertIn('городские корректировщики', records('StoryData/S504B.json')[143]['content'])
        for scene, ids in {'E405B': (16,), 'E406B': (58,), 'E407A': (19,),
                           'S502B': (46, 112, 133), 'S504B': (98,)}.items():
            scene_records = records(f'StoryData/{scene}.json')
            for record_id in ids:
                self.assertIn('Измаил', scene_records[record_id]['content'])

    def test_identity_title_and_battle_effect_regressions(self):
        self.assertEqual(records('Personalities.json')[11114]['title'], 'Авангард Уджат LCA\nЛидер 3-й команды')
        gregor = records('Skills_Ego_Personality-12.json')[2120711]
        for level in gregor['levelList']:
            self.assertIn('её подкидывания.\n', level['desc'])
        hong_lu = records('Skills_personality-06.json')
        for skill_id in range(1061501, 1061505):
            raw = json.dumps(hong_lu[skill_id], ensure_ascii=False)
            self.assertNotIn('[TiedRopeHonglu:`', raw)
            self.assertIn('[TiedRopeHonglu]', raw)
        keywords = records('BattleKeywords.json')
        buffs = records('Bufs.json')
        self.assertEqual(keywords['WindBladeIshmael']['name'], buffs['WindBladeIshmael']['name'])

    def test_scanner_reports_aligned_nested_text_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ru_path = root / 'ru/StoryData/Scene.json'
            paths = [ru_path, root / 'source/en/StoryData/EN_Scene.json', root / 'source/kr/StoryData/KR_Scene.json']
            texts = ['Я уже получил письмо, Исмаиль.', 'I already got the letter, Ishmael.', '편지는 이미 받았어요, 이스마엘.']
            for path, value in zip(paths, texts):
                path.parent.mkdir(parents=True)
                payload = {'dataList': [{'id': 42, 'model': '이스마엘', 'content': value}]}
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            original = ru_path.read_bytes()
            report = scan(root / 'ru', root / 'source')
            self.assertEqual(report['counts'], {'ishmael_name': 1, 'speaker_gender': 1})
            row, = report['findings']
            self.assertEqual(row['path'], ('dataList', 0, 'content'))
            self.assertEqual(row['en'], texts[1])
            self.assertEqual(row['kr'], texts[2])
            self.assertEqual(ru_path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
