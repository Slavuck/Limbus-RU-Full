"""Report suspected localization defects in context, without modifying the pack."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from audit_localization_diff import is_visible_source
from localization_common import (
    build_json_index,
    is_technical_key,
    load_json,
    visible_key,
    walk_aligned_strings,
    write_json,
)


STORY_NAME = re.compile(r'\b(?:ишма[эе]л[ьяюе]?|исма[ие]л(?:ь|а|у|ом|е|я|ю|ем)?|'
                        r'изма[ие]л(?:ь|а|у|ом|е|я|ю|ем))\b', re.IGNORECASE)
OUTIS_NAME = re.compile(r'\b(?:аутис[ауе]?|оутис[ауе]?|отис(?:а|у|ом|е))\b', re.IGNORECASE)
FIXER = re.compile(r'\bфиксер(?:а|у|ом|е|ы|ов|ам|ами|ах|ша|ши)?\b', re.IGNORECASE)
ADDRESS = re.compile(r'\bгосподин(?:а|у|ом|е)?\s+(?:Отис|Измаил|Фауст|Р[ёе]шу|Дон Кихот)\b', re.IGNORECASE)
GENDER = re.compile(r'\bя\s+(?:(?:уже|бы|не|ещ[её]|только|сам|вс[её]|и)\s+){0,3}'
                    r'(?:мог|хотел|сказал|сделал|знал|получил|решил|понял|приш[её]л|'
                    r'видел|думал|был|готов|должен|рад|уверен|согласен|заметил)\b', re.IGNORECASE)
FEMALE_SPEAKER = re.compile(r'^(?:Измаил|Отис|Фауст|Р[ёе]шу|Дон Кихот)$', re.IGNORECASE)
FEMALE_MODELS = {'이스마엘', '오티스', '파우스트', '료슈', '돈키호테', '돈키호테1', '돈키호테2'}
PREPOSITION = re.compile(r'\b(?:уповани\w*|взгляну\w*|обрат\w+\s+внимание) не\s+\w+', re.IGNORECASE)
DOUBLE_DOT = re.compile(r'(?<=[А-ЯЁа-яё])\.{2}(?![.!?])')
TAG = re.compile(r'<[^>]+>')
SQUARE_KEY = re.compile(r'\[([A-Za-z][A-Za-z0-9_]+)\]')
RICH_LABEL = re.compile(r'\[([A-Za-z][A-Za-z0-9_]+):`([^`]+)`\]')
LINK_LABEL = re.compile(r'<link=["\']?([A-Za-z0-9_]+)["\']?>.*?</link>')
LEGACY_TAIL = re.compile(r'\(;[A-Za-z0-9_]+\)')
AFTER_EFFECT = re.compile(r'\[([A-Za-z][A-Za-z0-9_]+)\](?:\s+\d+)?\s*\(([^()\r\n]+)\)')
PARENTHETICAL = re.compile(r'\(([^()\r\n]+)\)')
UNKNOWN = re.compile(r'\bUnknown\b', re.IGNORECASE)


def plain_text(value):
    return TAG.sub('', value or '')


def longest_line(value):
    return max(map(len, plain_text(value).splitlines()), default=0)


def effect_names(root, prefix=''):
    names = {}
    for family in ('BattleKeywords', 'Bufs'):
        for path in sorted(root.rglob(f'{prefix}{family}*.json')):
            for row in load_json(path)['dataList']:
                if isinstance(row.get('name'), str):
                    names.setdefault(str(row['id']), set()).add(row['name'].casefold())
    return names


def classify(relative, leaf, effects, source_effects, known_names, story_models):
    value = leaf.output
    rules = {
        'ishmael_name': STORY_NAME,
        'outis_name': OUTIS_NAME,
        'fixer_term': FIXER,
        'honorific': ADDRESS,
        'preposition': PREPOSITION,
        'double_dot': DOUBLE_DOT,
        'unknown': UNKNOWN,
        'legacy_effect_tail': LEGACY_TAIL,
    }
    for category, pattern in rules.items():
        for match in pattern.finditer(value):
            yield category, match.group()
    model = story_models.get((leaf.object_id or {}).get('id'))
    if model in FEMALE_MODELS or FEMALE_SPEAKER.fullmatch(leaf.speaker or ''):
        for match in GENDER.finditer(value):
            yield 'speaker_gender', match.group()

    if relative == 'Personalities.json' and leaf.key == 'title':
        ru_width = longest_line(value)
        en_width = longest_line(leaf.english)
        lost_line_break = value.count('\n') < (leaf.english or '').count('\n')
        if ru_width >= 30 and (ru_width >= en_width + 8 or lost_line_break):
            yield 'identity_title_width', str(ru_width)

    if leaf.key not in {'desc', 'summary', 'undefined', 'flavor'}:
        return
    for match in RICH_LABEL.finditer(value):
        key, label = match.groups()
        if SQUARE_KEY.search(label):
            yield 'nested_effect_label', match.group()
        if key not in effects:
            yield 'unresolved_custom_effect', key
    normalized_effects = plain_text(LINK_LABEL.sub(r'[\1]', value))
    for match in AFTER_EFFECT.finditer(normalized_effects):
        key, label = match.groups()
        if label.strip().casefold() in effects.get(key, ()):
            yield 'duplicate_effect_name', match.group()
    if relative.startswith(('Skills', 'Passives', 'BattleKeywords', 'Bufs')):
        for key in SQUARE_KEY.findall(normalized_effects):
            if key in source_effects and key not in effects:
                yield 'missing_effect_key', key
        for match in PARENTHETICAL.finditer(normalized_effects):
            label = match.group(1).strip()
            if label.casefold() in known_names or label in effects:
                yield 'parenthetical_effect_name', match.group()
    for match in LINK_LABEL.finditer(value):
        key = match.group(1)
        if key not in effects and key not in (leaf.english or '') and key not in (leaf.korean or ''):
            yield 'unresolved_custom_link', key


def scan(ru, source):
    en, kr = (build_json_index(source / lang)[0] for lang in ('en', 'kr'))
    files, duplicates = build_json_index(ru)
    if duplicates:
        raise ValueError(f'Ambiguous paths in Russian pack: {duplicates}')
    if not files or not en or not kr:
        raise ValueError('Expected nonempty RU, EN and KR localization trees')
    effects = effect_names(ru)
    source_effects = effect_names(source / 'en', 'EN_').keys() | effect_names(source / 'kr', 'KR_').keys()
    known_names = set().union(*effects.values())
    findings = []
    count = 0
    for key, file in sorted(files.items()):
        relative = file.relative_to(ru).as_posix()
        en_doc = load_json(en[key]) if key in en else None
        kr_doc = load_json(kr[key]) if key in kr else None
        ru_doc = load_json(file)
        story_models = {}
        if relative.startswith('StoryData/') and isinstance(ru_doc, dict):
            story_models = {row['id']: row.get('model') for row in ru_doc.get('dataList', [])
                            if isinstance(row, dict) and 'id' in row}
        for leaf in walk_aligned_strings(ru_doc, en_doc, kr_doc):
            if not leaf.output.strip() or is_technical_key(leaf.key):
                continue
            if not (visible_key(leaf.key) or is_visible_source(leaf.english, leaf.key)):
                continue
            count += 1
            matches = sorted(set(classify(relative, leaf, effects, source_effects, known_names, story_models)))
            if not matches:
                continue
            findings.append({'file': relative, 'path': leaf.path_parts, 'id': leaf.object_id,
                             'speaker': leaf.speaker or story_models.get((leaf.object_id or {}).get('id')),
                             'scene': leaf.scene, 'ru': leaf.output,
                             'en': leaf.english, 'kr': leaf.korean, 'matches': matches})
    counts = Counter(category for row in findings for category, _ in row['matches'])
    return {'files': len(files), 'strings': count, 'counts': dict(sorted(counts.items())), 'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ru', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True, help='Official localization root with en/ and kr/')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    for root in (args.ru, args.source):
        if args.report.resolve().is_relative_to(root.resolve()):
            parser.error('The report must be outside the localization trees')
    result = scan(args.ru, args.source)
    write_json(args.report, result)
    print(json.dumps({key: value for key, value in result.items() if key != 'findings'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
