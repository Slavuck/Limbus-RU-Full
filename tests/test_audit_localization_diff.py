from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_localization_diff import (
    Auditor,
    baseline_candidates,
    canonical_path,
    create_snapshot,
    intentional_literal_reason,
)
from scripts.sync_localization_structure import merge_structure


class AuditLocalizationDiffTests(unittest.TestCase):
    def auditor(self) -> Auditor:
        return Auditor({}, {})

    def test_normalizes_language_prefixes_and_separators(self) -> None:
        self.assertEqual(canonical_path(r"StoryData\EN_P10001.json"), "StoryData/P10001.json")
        self.assertEqual(canonical_path("KR_Foo.json"), "Foo.json")

    def test_stable_id_reordering_is_not_a_structure_change(self) -> None:
        en = {"dataList": [{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}]}
        ru = {"dataList": [{"id": 2, "name": "Два"}, {"id": 1, "name": "Один"}]}
        auditor = self.auditor()
        auditor.compare_file("Names.json", en, en, ru)
        self.assertEqual(auditor.state.missing_structure, [])

    def test_duplicate_ids_keep_leaf_identity_for_source_history(self) -> None:
        stable = json.dumps({"id": 0}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        baseline = {
            ("story.json", stable, "content"): [
                {"previous_english": "First", "previous_russian": "Первый", "json_path": "$.dataList[0].content"},
                {"previous_english": "Second", "previous_russian": "Второй", "json_path": "$.dataList[1].content"},
            ]
        }
        auditor = Auditor(baseline, {})
        source = {"dataList": [{"id": 0, "content": "First"}, {"id": 0, "content": "Second"}]}
        russian = {"dataList": [{"id": 0, "content": "Первый"}, {"id": 0, "content": "Второй"}]}
        auditor.compare_file("Story.json", source, source, russian)
        self.assertEqual(auditor.state.changed_source, [])

    def test_new_object_and_new_file_are_reported(self) -> None:
        auditor = self.auditor()
        en = {"dataList": [{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}]}
        ru = {"dataList": [{"id": 1, "name": "Один"}]}
        auditor.compare_file("Names.json", en, en, ru)
        self.assertTrue(any(row["kind"] == "missing_object" for row in auditor.state.missing_structure))

    def test_changed_source_uses_previous_index(self) -> None:
        baseline = {
            ("names.json", json.dumps({"id": 1}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "desc"): [
                {"previous_english": "Old wording", "previous_russian": "Старая формулировка", "json_path": "$.dataList[0].desc"}
            ]
        }
        auditor = Auditor(baseline, {})
        auditor.compare_file(
            "Names.json",
            {"dataList": [{"id": 1, "desc": "New wording"}]},
            {"dataList": [{"id": 1, "desc": "새 문구"}]},
            {"dataList": [{"id": 1, "desc": "Старая формулировка"}]},
        )
        self.assertEqual(len(auditor.state.changed_source), 1)
        self.assertEqual(auditor.state.changed_source[0]["status"], "pending")

    def test_moved_positional_text_matches_exact_source_before_old_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            index_path = Path(temporary) / "source_index.jsonl"
            rows = [
                {
                    "normalized_file": "ActionEvents.json",
                    "stable_id": {"id": 1},
                    "field": "result",
                    "json_path": "$.dataList[0].options[0].result[0]",
                    "semantic_path": ["dataList", "@id=1", "options", "#0", "result", "#0"],
                    "new_english_value": "First result.",
                    "current_russian_value": "Первый результат.",
                },
                {
                    "normalized_file": "ActionEvents.json",
                    "stable_id": {"id": 1},
                    "field": "result",
                    "json_path": "$.dataList[0].options[1].result[0]",
                    "semantic_path": ["dataList", "@id=1", "options", "#1", "result", "#0"],
                    "new_english_value": "Second result.",
                    "current_russian_value": "Второй результат.",
                },
            ]
            index_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            auditor = Auditor(baseline_candidates(index_path), {}, full_review=True)
            english = {"dataList": [{"id": 1, "options": [{"result": ["Second result."]}, {"result": ["First result."]}]}]}
            russian = {"dataList": [{"id": 1, "options": [{"result": ["Второй результат."]}, {"result": ["Первый результат."]}]}]}
            auditor.compare_file("ActionEvents.json", english, {}, russian)
            self.assertEqual(auditor.state.changed_source, [])

    def test_technical_values_are_excluded_from_untranslated(self) -> None:
        auditor = self.auditor()
        auditor.compare_file("A.json", {"id": "INTERNAL_ID", "name": "Hello world."}, {}, {"id": "INTERNAL_ID", "name": "Hello world."})
        self.assertEqual([row["english"] for row in auditor.state.untranslated], ["Hello world."])

    def test_untranslated_visible_text_is_found(self) -> None:
        auditor = self.auditor()
        auditor.compare_file("A.json", {"desc": "A visible sentence."}, {}, {"desc": "A visible sentence."})
        self.assertEqual(len(auditor.state.untranslated), 1)
        self.assertEqual(auditor.state.full_review[0]["status"], "pending")

    def test_repeated_placeholder_loss_is_detected(self) -> None:
        auditor = Auditor({}, {}, review_scope=({("a.json", "{}", "desc")}, set()), full_review=True)
        auditor.compare_file(
            "A.json",
            {"desc": "Use {0}, then {0}."},
            {},
            {"desc": "Используйте {0}."},
        )
        self.assertEqual(len(auditor.state.format_errors), 1)

    def test_repeated_game_tag_loss_is_detected(self) -> None:
        auditor = Auditor({}, {}, review_scope=({("a.json", "{}", "desc")}, set()), full_review=True)
        auditor.compare_file(
            "A.json",
            {"desc": "Gain [Haste], then gain [Haste]."},
            {},
            {"desc": "Получает [Haste]."},
        )
        self.assertEqual(len(auditor.state.format_errors), 1)

    def test_game_tag_preserved_by_korean_is_still_required(self) -> None:
        auditor = Auditor({}, {}, review_scope=({("a.json", "{}", "desc")}, set()), full_review=True)
        auditor.compare_file(
            "A.json",
            {"desc": "Gain [Haste]."},
            {"desc": "[Haste] 획득"},
            {"desc": "Получает Спешку."},
        )
        self.assertEqual(len(auditor.state.format_errors), 1)

    def test_localizable_bracket_label_follows_korean_context(self) -> None:
        auditor = Auditor({}, {}, review_scope=({("a.json", "{}", "name")}, set()), full_review=True)
        auditor.compare_file(
            "A.json",
            {"name": "Shade of Reflection [Chachihu]"},
            {"name": "사영 [삽시호]"},
            {"name": "Тень преломления [Чачиху]"},
        )
        self.assertEqual(auditor.state.format_errors, [])
        self.assertEqual(auditor.state.full_review[0]["status"], "reviewed")

    def test_english_ui_tag_is_required_when_korean_uses_other_markup(self) -> None:
        auditor = Auditor({}, {}, review_scope=({("a.json", "{}", "desc")}, set()), full_review=True)
        auditor.compare_file(
            "A.json",
            {"desc": "Tigermark Round[TabExplain] Reload[TabExplain]"},
            {"desc": "<noparse>호표탄</noparse> 장전"},
            {"desc": "Патрон «Тигр-марка» Перезарядка"},
        )
        self.assertEqual(len(auditor.state.format_errors), 1)

    def test_missing_russian_text_is_reported_as_untranslated(self) -> None:
        auditor = self.auditor()
        auditor.compare_file("A.json", {"desc": "A visible sentence."}, {}, {})
        self.assertEqual(len(auditor.state.untranslated), 1)
        self.assertIsNone(auditor.state.untranslated[0]["current_russian"])

    def test_full_review_finds_untranslated_text_without_previous_scope(self) -> None:
        auditor = Auditor({}, {}, update_files=set(), full_review=True)
        auditor.compare_file("A.json", {"desc": "A visible sentence."}, {}, {"desc": "A visible sentence."})
        self.assertEqual(len(auditor.state.full_review), 1)

    def test_full_review_still_excludes_technical_strings(self) -> None:
        auditor = Auditor({}, {}, full_review=True)
        auditor.compare_file("A.json", {"id": "INTERNAL_ID"}, {}, {"id": "INTERNAL_ID"})
        self.assertEqual(auditor.state.full_review, [])

    def test_recorded_translation_remains_in_next_full_review(self) -> None:
        initial = Auditor({}, {}, full_review=True)
        source = {"desc": "New visible text."}
        initial.compare_file("A.json", source, {}, {})
        queue_id = initial.state.full_review[0]["queue_id"]
        reviewed = Auditor(
            {},
            {},
            decisions={queue_id: {"status": "reviewed", "reason": "translated_for_current_update"}},
            full_review=True,
        )
        reviewed.compare_file("A.json", source, {}, {"desc": "Новый видимый текст."})
        self.assertEqual(len(reviewed.state.full_review), 1)
        self.assertEqual(reviewed.state.full_review[0]["status"], "reviewed")

    def test_translated_leaf_absent_from_previous_snapshot_stays_in_scope(self) -> None:
        auditor = Auditor({}, {}, full_review=True, previous_output_locators=set())
        auditor.compare_file(
            "New.json",
            {"desc": "New visible text."},
            {},
            {"desc": "Новый видимый текст."},
        )
        self.assertEqual(len(auditor.state.full_review), 1)
        self.assertEqual(auditor.state.full_review[0]["status"], "reviewed")

    def test_new_visible_leaf_is_audited_even_before_structure_sync(self) -> None:
        auditor = Auditor({}, {}, update_files=set())
        auditor.compare_file("New.json", {"desc": "New visible text."}, {}, {})
        self.assertEqual(len(auditor.state.untranslated), 1)

    def test_snapshot_records_requested_target_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            en, kr, ru, snapshot = (root / name for name in ("en", "kr", "ru", "snapshot"))
            for directory in (en, kr, ru):
                directory.mkdir()
                (directory / "A.json").write_text('{"name": "x"}', encoding="utf-8")
            manifest_path = create_snapshot(en, kr, ru, snapshot, "1.112.0-post-2026-08-20")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["target_version"], "1.112.0-post-2026-08-20")
            self.assertEqual(manifest["purpose"], "pre-1.112.0-post-2026-08-20 localization backup")

    def test_confirmed_literal_can_be_intentional(self) -> None:
        self.assertEqual(intentional_literal_reason("E.G.O", "name"), "confirmed_game_literal")

    def test_new_proper_name_is_not_automatically_intentional(self) -> None:
        self.assertIsNone(intentional_literal_reason("Virescent Flame Palm", "name"))

    def test_structure_sync_adds_objects_and_preserves_translation(self) -> None:
        en = {"dataList": [{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}]}
        ru = {"dataList": [{"id": 1, "name": "Один"}]}
        merged = merge_structure(en, ru)
        self.assertEqual(merged["dataList"][0]["name"], "Один")
        self.assertEqual(merged["dataList"][1]["name"], "Two")


if __name__ == "__main__":
    unittest.main()
