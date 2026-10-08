import unittest

from jp_patch.locres import Entry, dumps, loads
from jp_patch.runtime_text import SHADER_KEY, SHADER_SOURCE_HASH, runtime_text


class RuntimeTextTests(unittest.TestCase):
    def row(self, **changes):
        return dict(namespace=SHADER_KEY[0], namespace_hash=1,
                    key=SHADER_KEY[1], key_hash=2, source_hash=SHADER_SOURCE_HASH,
                    ja='自作の見出し\n自作の説明') | changes

    def test_shader_lines_survive_locres_and_widget_crlf_split(self):
        row = self.row()
        entry = Entry(**{k: row[k] for k in ('namespace', 'namespace_hash', 'key', 'key_hash', 'source_hash')}, text=runtime_text(row))
        rendered = loads(dumps([entry]))[0].text
        lines = rendered.split('\r\n')
        self.assertEqual(lines, ['自作の見出し', '自作の説明'])
        self.assertEqual(row['ja'], '自作の見出し\n自作の説明')

    def test_other_widgets_keep_their_text(self):
        for changes in ({'namespace': '別の名前空間'}, {'key': '別のキー'}):
            row = self.row(**changes)
            self.assertEqual(runtime_text(row), row['ja'])

    def test_changed_source_requires_reinspection(self):
        with self.assertRaises(ValueError):
            runtime_text(self.row(source_hash=0))
