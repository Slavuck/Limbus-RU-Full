import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_game_update import removed_source_rows, delta


class AuditGameUpdateTests(unittest.TestCase):
    def test_removed_id_is_reported_even_if_array_position_is_reused(self):
        previous = [{'normalized_file': 'EN_A.json', 'semantic_path': ['dataList', '@id=1', 'desc'],
                     'new_english_value': 'Old hint', 'new_korean_value': '이전 힌트'}]
        current = [{'normalized_file': 'A.json', 'semantic_path': ['dataList', '@id=2', 'desc']}]
        with tempfile.TemporaryDirectory() as temporary:
            ru = Path(temporary)
            (ru/'A.json').write_text(json.dumps({'dataList': [{'id': 1, 'desc': 'Старая подсказка'}]}), 'utf-8')
            deleted, obsolete = removed_source_rows(iter(previous), iter(current), ru)
            self.assertEqual(len(deleted), 1)
            self.assertEqual(len(obsolete), 1)
            (ru/'A.json').write_text(json.dumps({'dataList': [{'id': 2, 'desc': 'Новая подсказка'}]}), 'utf-8')
            deleted, obsolete = removed_source_rows(iter(previous), iter(current), ru)
            self.assertEqual(len(deleted), 1)
            self.assertEqual(obsolete, [])

    def test_reordering_does_not_look_like_removed_text(self):
        rows = [{'normalized_file': 'A.json', 'semantic_path': ['dataList', f'@id={i}', 'desc']}
                for i in (1, 2)]
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(removed_source_rows(iter(rows), iter(reversed(rows)), Path(temporary)), ([], []))

    def test_file_delta_tracks_changed_and_deleted_korean_resources(self):
        before = {'files': [{'path': 'KR_A.json', 'sha256': 'old'}, {'path': 'notes.json', 'sha256': 'same'}]}
        after = {'files': [{'path': 'KR_A.json', 'sha256': 'new'}, {'path': 'KR_B.json', 'sha256': 'added'}]}
        self.assertEqual(delta(before, after), {'added': ['KR_B.json'], 'deleted': ['notes.json'], 'changed': ['KR_A.json']})


if __name__ == '__main__':
    unittest.main()
