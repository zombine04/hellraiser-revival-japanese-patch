from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call

from jp_patch.release import GitHub, publish


class ReleaseLookupTests(unittest.TestCase):
    def test_draft_uses_reviewed_release_notes(self):
        notes=Path('docs/releases/v1.0.0.md')
        github=GitHub('example/test',notes_file=notes)
        github.cli=Mock()
        github.create_draft('v1.0.0','a'*40)
        args=github.cli.call_args.args
        self.assertEqual(args[-2:],('--notes-file',str(notes)))
        self.assertNotIn('--generate-notes',args)
        self.assertIn('--draft',args)

    def test_draft_without_tag_is_found_on_later_page(self):
        github=GitHub('example/test')
        unrelated=[dict(draft=False,tag_name=f'v0.0.{i}') for i in range(100)]
        draft=dict(id=123,draft=True,tag_name='v1.0.0',target_commitish='a'*40,assets=[])
        github.api=Mock(side_effect=[None,unrelated,[draft]])
        self.assertEqual(github.release('v1.0.0'),draft)
        self.assertEqual(github.api.call_args_list,[
            call('releases/tags/v1.0.0',missing=True),
            call('releases?per_page=100&page=1'),
            call('releases?per_page=100&page=2'),
        ])

    def test_published_release_does_not_need_draft_lookup(self):
        github=GitHub('example/test')
        published=dict(draft=False,tag_name='v1.0.0')
        github.api=Mock(return_value=published)
        self.assertEqual(github.release('v1.0.0'),published)
        github.api.assert_called_once_with('releases/tags/v1.0.0',missing=True)

    def test_absent_release_does_not_match_other_draft(self):
        github=GitHub('example/test')
        github.api=Mock(side_effect=[None,[dict(draft=True,tag_name='v2.0.0')]])
        self.assertIsNone(github.release('v1.0.0'))


class FakeGitHub:
    def __init__(self):
        self.current=None
        self.reference=None
        self.assets={}
        self.creates=0
        self.publications=0
        self.corrupt=False
    def tag_commit(self,tag): return self.reference
    def release(self,tag): return self.current
    def create_draft(self,tag,commit):
        self.creates+=1
        self.current=dict(draft=True,target_commitish=commit,assets=[])
    def upload(self,tag,files):
        self.assets={file.name:file.read_bytes() for file in files}
        self.current['assets']=[dict(name=name) for name in self.assets]
    def download(self,tag,names,folder):
        for name in names: (folder/name).write_bytes(b'bad' if self.corrupt else self.assets[name])
    def publish(self,tag):
        self.publications+=1
        self.current['draft']=False
        self.reference=self.current['target_commitish']


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.files=[Path(self.temp.name)/name for name in ('sample.zip','sample.sha256')]
        for file in self.files: file.write_bytes(b'self-made')
        self.github=FakeGitHub()

    def run_publish(self): return publish(self.github,'v1.0.0','a'*40,self.files)

    def test_rerun_is_idempotent(self):
        self.run_publish(); self.run_publish()
        self.assertEqual((self.github.creates,self.github.publications),(1,1))

    def test_failure_stays_draft_and_retry_recovers(self):
        self.github.corrupt=True
        with self.assertRaises(ValueError): self.run_publish()
        self.assertEqual(self.github.publications,0)
        self.assertTrue(self.github.current['draft'])
        self.github.corrupt=False
        self.run_publish()
        self.assertEqual((self.github.creates,self.github.publications),(1,1))

    def test_existing_tag_other_commit_is_rejected(self):
        self.github.reference='b'*40
        with self.assertRaises(ValueError): self.run_publish()
        self.assertEqual(self.github.creates,0)

    def test_unavailable_created_draft_stops_before_upload(self):
        self.github.release=Mock(return_value=None)
        with self.assertRaisesRegex(ValueError,'ドラフトReleaseを取得できません'):
            self.run_publish()
        self.assertEqual(self.github.creates,1)
        self.assertEqual(self.github.publications,0)
        self.assertEqual(self.github.assets,{})

    def test_published_assets_are_not_replaced(self):
        self.run_publish()
        self.files[0].write_bytes(b'changed')
        with self.assertRaises(ValueError): self.run_publish()
        self.assertEqual(self.github.assets[self.files[0].name],b'self-made')
