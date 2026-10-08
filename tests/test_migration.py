import unittest

from jp_patch.catalog import metadata
from jp_patch.locres import Entry
from jp_patch.migration import migrate


def catalog(*entries):
    return dict(schema_version=1, game_version='self-authored', entries=[metadata(entry) for entry in entries])


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.entry = Entry('自作', 1, 'key', 2, 3, 'Self-authored example')
        self.row = self.entry.metadata() | dict(ja='自作の訳文', status='reviewed', display_checked=True)

    def test_exact_match_keeps_review_but_resets_display(self):
        rows, report = migrate(catalog(self.entry), catalog(self.entry), [self.row])
        self.assertEqual(rows, [self.row | {'display_checked': False}])
        self.assertEqual(report['counts']['reused'], 1)
        self.assertTrue(self.row['display_checked'])

    def test_text_digest_change_even_with_same_source_hash_is_not_reused(self):
        changed = Entry('自作', 1, 'key', 2, 3, 'Different self-authored example')
        rows, report = migrate(catalog(self.entry), catalog(changed), [self.row])
        self.assertEqual(rows[0]['ja'], '')
        self.assertEqual(rows[0]['status'], 'untranslated')
        self.assertEqual(report['counts']['changed'], 1)

    def test_new_removed_and_same_text_under_different_key(self):
        added = Entry('自作', 1, 'other', 4, 3, self.entry.text)
        rows, report = migrate(catalog(self.entry), catalog(added), [self.row])
        self.assertEqual(rows[0]['ja'], '')
        self.assertEqual(report['counts']['added'], 1)
        self.assertEqual(report['counts']['removed'], 1)

    def test_changed_hash_and_format_use_new_metadata(self):
        changed = Entry('自作', 1, 'key', 2, 99, 'Self-authored {Count}')
        rows, report = migrate(catalog(self.entry), catalog(changed), [self.row])
        self.assertEqual(rows[0]['source_hash'], 99)
        self.assertEqual(rows[0]['status'], 'untranslated')

    def test_region_scope_is_not_mixed(self):
        other = self.row | {'ja': '別領域の訳'}
        game, _ = migrate(catalog(self.entry), catalog(self.entry), [self.row])
        engine, _ = migrate(catalog(self.entry), catalog(self.entry), [other])
        self.assertNotEqual(game[0]['ja'], engine[0]['ja'])

    def test_bad_baseline_and_duplicates_are_rejected(self):
        for rows in ([self.row | {'source_hash': 99}], [self.row, self.row]):
            with self.assertRaises(ValueError):
                migrate(catalog(self.entry), catalog(self.entry), rows)

    def test_missing_translation_stays_untranslated(self):
        rows, report = migrate(catalog(self.entry), catalog(self.entry), [])
        self.assertEqual(rows[0]['status'], 'untranslated')
        self.assertEqual(report['counts']['missing'], 1)
