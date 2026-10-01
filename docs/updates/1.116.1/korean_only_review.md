# Проверка файлов, присутствующих только в корейском пакете

Проверен список `korean_without_english` из `reports/updates/current-2026-10-01/file_pairing.json` против нормализованного индекса файлов актуальных пакетов EN/KR. Все 54 пути существуют в KR и не имеют соответствующего нормализованного пути в EN.

## Сводка содержимого

- У **44 из 54 файлов** нет ни одной непустой строковой записи в JSON. Это пустые по локализуемому тексту файлы, а не обязательно физически пустые файлы: обычно содержат пустой `dataList`.
- У остальных **10 файлов** есть строковое содержимое: `rpg-dialogue-text-data-floor-7-c2.json` (106 непустых строк), два `rpg-loc-dialogue-theater-*.json` (по 1 текстовой строке), `rpg-loc-npc-floor-2-c1-enemy.json` (имя `???`) и шесть файлов `StoryData` (в сумме 281 непустая строка).

Таким образом, предположение о 45 пустых файлах не подтвердилось: по этому критерию их 44.

### 44 файла без непустых строк

**Верхний уровень:** `Passive_Ego-a1c9p2.json`, `Passives-a1c9p1.json`, `Passives-a1c9p2.json`, `Passives-a1c9p3.json`, `Passives_Enemy-a1c9p3.json`, `Personalities-a1c9p2.json`, `Skills_Ego_Personality-a1c9p2.json`, `Skills_Enemy-a1c9p2.json`, `Skills_Enemy-a1c9p3.json`, `Skills_personality-a1c9p1.json`, `Skills_personality-a1c9p2.json`, `UserTicket-EGOBg-a1c9p3.json`, `UserTicket-L-a1c9p3.json`, `UserTicket-R-a1c9p3.json`.

**RPGSystem:** `rpg-loc-dialogue-choice-floor-1-c1.json`, `rpg-loc-dialogue-choice-floor-1-c2.json`, `rpg-loc-dialogue-choice-floor-2-c2.json`, `rpg-loc-dialogue-choice-floor-3-c2.json`, `rpg-loc-dialogue-choice-floor-4-c2.json`, `rpg-loc-dialogue-choice-floor-5-c2.json`; `rpg-loc-location-floor-1-b.json`, `rpg-loc-location-floor-1-c1.json`, `rpg-loc-location-floor-1-c2.json`, `rpg-loc-location-floor-2-b.json`, `rpg-loc-location-floor-2-c1.json`, `rpg-loc-location-floor-2-c2.json`, `rpg-loc-location-floor-3-b.json`, `rpg-loc-location-floor-3-c2.json`, `rpg-loc-location-floor-5-c2.json`; `rpg-loc-narration-floor-1-b.json`, `rpg-loc-narration-floor-1-c1.json`, `rpg-loc-narration-floor-1-c2.json`, `rpg-loc-narration-floor-1.json`, `rpg-loc-narration-floor-2-c1.json`, `rpg-loc-narration-floor-2-c2.json`, `rpg-loc-narration-floor-4-c2.json`, `rpg-loc-narration-floor-7-c2.json`; `rpg-loc-npc-floor-2-c1.json`, `rpg-loc-npc-floor-3-c2.json`, `rpg-loc-npc-floor-7-c2-enemy.json`, `rpg-loc-quest-floor-2-c2.json`, `rpg-loc-quest-floor-3-c2.json`, `rpg-loc-quest-floor-4-c2.json`, `rpg-loc-swarm-mob-floor-2-c1.json`.

### Непустые файлы и наблюдения

- `RPGSystem/rpg-loc-dialogue-theater-b.json` (`D_THB_LOCKED`) и `RPGSystem/rpg-loc-dialogue-theater-c.json` (`D_THC_LOCKED`) содержат каждый по одной фразе: `[미사용] 아직 관람할 수 없는 이야기입니다.` — «[Не используется] Эту историю пока нельзя посмотреть». Это подтверждает пометку `[미사용]` в самих строках. По одному локализационному файлу нельзя заключить, обращается ли к ним текущая игра.
- `RPGSystem/rpg-loc-npc-floor-2-c1-enemy.json` содержит запись `N102050` с `displayName: "???"`. Это подтверждённый placeholder, личность по этой записи не раскрывается.
- `RPGSystem/rpg-dialogue-text-data-floor-7-c2.json` содержит 106 непустых строк; файл остаётся KR-only относительно EN и требует отдельного решения по парности/переводу, если основной агент решит включить его в обновление.
- `StoryData/RPG1.json`: 2 записи, ID 0–1, пропусков поля `id` нет.
- `StoryData/S1039I.json`: 31 запись; поле `id` есть у позиций 0–15 (ID 0–15), у следующих 15 записей поле отсутствует.
- `StoryData/S1039I2.json`: 81 запись; поле `id` есть у позициях 0–15 (ID 0–15), у следующих 65 записей поле отсутствует.
- `StoryData/S1042C.json`: 9 записей, ID 0–8; `StoryData/S1043C.json`: 14 записей, ID 0–13; `StoryData/S1044C.json`: 13 записей, ID 0–12. Во всех трёх поле `id` присутствует у каждой записи, пропусков нет.
- Единственная найденная CG-заметка в этих файлах — `StoryData/S1044C.json`, запись 10: `로보토미 백야 cg` («Лоботомия: Белая ночь, CG»). Это буквальная строка в поле `content`; её назначение по самому JSON не устанавливается.

Суффиксы и имена файлов, поля ID, пустые массивы и пометка `[미사용]` зафиксированы как наблюдаемые данные. Они сами по себе не доказывают статус прототипа, активность или неиспользование файлов во время исполнения.

## Уточнение после проверки полей

`rpg-dialogue-text-data-floor-7-c2.json` не содержит реплик: все 106 непустых строк — значения технических полей `dialogueKey`, `portraitKey`, `voice`, `sfx`. Их перевод нарушил бы привязки ресурсов. Строки соответствующих диалогов находятся в парных `rpg-loc-dialogue-text` файлах и переведены. Файл привязок не добавляется в пользовательский языковой пакет.

## Сопоставление сюжетных вариантов

Повторная проверка по `content` с удалением пробелов нашла соответствия в других сюжетных файлах KR: RPG1 — 0/2, S1039I — 22/31, S1039I2 — 79/81, S1042C — 8/9, S1043C — 12/14, S1044C — 4/13. Это не означает, что остальные реплики отсутствуют в игре: варианты пунктуации, объединения реплик и черновые формулировки не дают точного совпадения. Их темы и контекст уже присутствуют в переводе парного сюжета: воспоминания о матери, разговор с Кармен, энергия Крыльев и власть основателей. Единственная CG-заметка явно не является художественной репликой.

RPG1 содержит самостоятельный вариант двух реплик Кромер: «Ух ты... вы только что...» / «Вышли оттуда?». Материал рассмотрен, но файлы с отсутствующей английской парой и неполными ID не инжектируются в пакет по предположению об их runtime-загрузке. Текущий пользовательский языковой пакет сохраняет полный состав актуального английского набора; статус загрузки корейских альтернатив остаётся не подтверждённым.
