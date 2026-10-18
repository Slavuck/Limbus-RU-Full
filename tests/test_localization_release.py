from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALIZE = ROOT / "Localize" / "Limbus-RU-Full"


def load(relative: str) -> dict:
    with (LOCALIZE / relative).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class LocalizationReleaseTests(unittest.TestCase):
    def test_yi_sang_executes_a_prescript_rather_than_a_person(self) -> None:
        passive = next(row for row in load('Passives.json')['dataList'] if row['id'] == 1011503)
        paragraph = next(part for part in passive['desc'].split('\n\n')
                         if '[IndexPrescriptYi_2]' in part)
        self.assertNotIn('казн', paragraph.lower())
        self.assertIn('выполнил [IndexPrescriptYi_2]', paragraph)
        self.assertIn('[UnlockBuffAlly_2]', paragraph)
        self.assertIn('4 СД', paragraph)
        self.assertIn('раз за ход', paragraph)

    def test_all_localization_json_files_parse(self) -> None:
        paths = sorted(LOCALIZE.rglob("*.json"))
        self.assertEqual(len(paths), 2370)
        for path in paths:
            with path.open("r", encoding="utf-8-sig") as handle:
                json.load(handle)

    def test_effie_saude_subtitles_distinguish_speakers(self) -> None:
        records = {
            row["id"]: row["dlg"]
            for row in load("BattleAnnouncerDlg/Announcer_EpiSode_7.json")["dataList"]
        }
        self.assertEqual(len(records), 29)
        for text in records.values():
            self.assertTrue(text.startswith("- "))
            self.assertIn("\n- ", text)
        self.assertIn("<i>что-то</i>", records["announcer_ally_specialdebuff_7_1"])

    def test_new_mirror_dungeon_rental_name_is_translated(self) -> None:
        records = {
            row["id"]: row["content"]
            for row in load("MirrorDungeonRentalName.json")["dataList"]
        }
        self.assertEqual(records[31], "Дыхание, Пронзающий")


if __name__ == "__main__":
    unittest.main()
