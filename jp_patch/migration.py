"""原文・識別情報・書式が一致した訳だけを別のゲーム版へ移す。"""
from .catalog import HASHES, IDENTITY, index, validate


def migrate(old_catalog, new_catalog, rows):
    validate(old_catalog, rows)
    before = index(old_catalog['entries'])
    after = index(new_catalog['entries'])
    translations = index(rows)
    result = []
    groups = {name: [] for name in ('reused', 'changed', 'added', 'missing', 'removed')}
    # 既存訳の順序を保ち、追加キーだけを末尾へ並べる。
    order = [tuple(row[key] for key in IDENTITY) for row in rows
             if tuple(row[key] for key in IDENTITY) in after]
    order.extend(sorted(after.keys() - set(order)))
    for identity in order:
        original = after[identity]
        reference = dict(zip(IDENTITY, identity))
        if identity not in before:
            category = 'added'
        elif before[identity] != original:
            category = 'changed'
        elif identity not in translations:
            category = 'missing'
        else:
            category = 'reused'
        groups[category].append(reference)
        if category == 'reused':
            row = translations[identity] | {'display_checked': False}
        else:
            row = {key: original[key] for key in IDENTITY + HASHES}
            row.update(ja='', status='untranslated', display_checked=False)
        result.append(row)
    groups['removed'] = [dict(zip(IDENTITY, identity)) for identity in sorted(before.keys() - after.keys())]
    validate(new_catalog, result)
    return result, {'counts': {name: len(keys) for name, keys in groups.items()}, 'keys': groups}
