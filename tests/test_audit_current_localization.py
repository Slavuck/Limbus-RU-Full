import tempfile
import unittest
from pathlib import Path

from scripts.audit_current_localization import default_ru, default_source
from scripts.audit_localization_diff import Auditor


class CurrentAuditTests(unittest.TestCase):
    def test_local_sources_take_precedence_over_installed_game_locator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for language in ('en', 'kr'):
                (root / 'input' / language).mkdir(parents=True)
            (root / 'input/расположение языковых пакетов.txt').write_text('"other"\nNotes', encoding='utf8')
            self.assertEqual(default_source(root), root / 'input')

    def test_quoted_locator_uses_only_first_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'input').mkdir()
            source = root / 'game source'
            (root / 'input/расположение языковых пакетов.txt').write_text(f'"{source}"\nOther instructions', encoding='utf-8-sig')
            self.assertEqual(default_source(root), source)

    def test_absent_source_requires_explicit_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(default_source(Path(temporary)))

    def test_working_output_and_publication_layout_are_both_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public = root / 'Localize/Limbus-RU-Full'
            public.mkdir(parents=True)
            self.assertEqual(default_ru(root), public)
            output = root / 'output/Limbus-RU-Full'
            output.mkdir(parents=True)
            self.assertEqual(default_ru(root), output)

    def test_changed_korean_metadata_does_not_translate_resource_ids(self):
        auditor = Auditor({}, {}, full_review=True)
        auditor.compare_file('A.json', {'dataList': [{'id': 1, 'model': 'asset_name'}]},
                             {'dataList': [{'id': 1, 'model': '모델'}]},
                             {'dataList': [{'id': 1, 'model': 'asset_name'}]})
        self.assertEqual(auditor.state.full_review, [])
        self.assertEqual(auditor.state.technical_mismatches, [])
        self.assertTrue(auditor.state.source_index)

    def test_technical_string_changes_are_still_blocking(self):
        auditor = Auditor({}, {}, full_review=True)
        auditor.compare_file('A.json', {'dataList': [{'id': 1, 'model': 'asset_name'}]},
                             {'dataList': [{'id': 1, 'model': '모델'}]},
                             {'dataList': [{'id': 1, 'model': 'переведённый ресурс'}]})
        self.assertEqual(len(auditor.state.technical_mismatches), 1)
        self.assertEqual(auditor.state.full_review, [])

    def test_text_edits_preserve_accepted_expanded_status_controls(self):
        source = 'Gain [Haste].'
        expanded = '<sprite name="Haste"><link="Haste">Спешки</link>'
        baseline = {('a.json', '{}', 'desc'): [{'previous_english': source,
                    'previous_korean': None, 'previous_russian': 'Получить ' + expanded}]}
        scope = ({('a.json', '{}', 'desc')}, set())
        auditor = Auditor(baseline, {}, review_scope=scope, full_review=True)
        auditor.compare_file('A.json', {'desc': source}, {}, {'desc': 'Союзник получает ' + expanded})
        self.assertEqual(auditor.state.format_errors, [])
        auditor = Auditor(baseline, {}, review_scope=scope, full_review=True)
        auditor.compare_file('A.json', {'desc': source}, {}, {'desc': 'Союзник получает Спешку'})
        self.assertEqual(len(auditor.state.format_errors), 1)


if __name__ == '__main__':
    unittest.main()
