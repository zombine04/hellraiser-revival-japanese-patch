"""GitHub CLIを用いる再実行可能なリリース処理。認証情報は出力しない。"""
import json
from pathlib import Path
import re
import subprocess
import tempfile


class GitHub:
    def __init__(self, repository, *, notes_file=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
            raise ValueError('リポジトリ指定が不正です')
        self.repository=repository
        self.notes_file=notes_file

    def cli(self,*args):
        result=subprocess.run(['gh',*args],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('GitHub CLIの操作に失敗しました。必要な権限とActionsの設定を確認してください。')
        return result.stdout

    def api(self,path,missing=False):
        result=subprocess.run(['gh','api',f'repos/{self.repository}/{path}'],capture_output=True,text=True)
        if result.returncode:
            if missing and '(HTTP 404)' in result.stderr:
                return None
            raise RuntimeError('GitHub APIの操作に失敗しました。認証情報は表示しません。')
        return json.loads(result.stdout)

    def release(self,tag):
        current=self.api('releases/tags/'+tag,missing=True)
        if current is not None:
            return current
        # 未公開ドラフトにはタグがなく、タグ指定APIは404を返す。
        page=1
        while True:
            releases=self.api(f'releases?per_page=100&page={page}')
            for release in releases:
                if release['draft'] and release['tag_name']==tag:
                    return release
            if len(releases)<100:
                return None
            page+=1

    def tag_commit(self,tag):
        reference=self.api('git/ref/tags/'+tag,missing=True)
        if reference is None:
            return None
        obj=reference['object']
        for _ in range(8):
            if obj['type']=='commit': return obj['sha']
            if obj['type']!='tag': break
            obj=self.api('git/tags/'+obj['sha'])['object']
        raise ValueError('タグの参照先を確定できません')

    def create_draft(self,tag,commit):
        notes=['--notes-file',str(self.notes_file)] if self.notes_file else ['--generate-notes']
        self.cli('release','create',tag,'--repo',self.repository,'--draft','--target',commit,'--title','日本語化パッチ '+tag,*notes)

    def upload(self,tag,files):
        self.cli('release','upload',tag,'--repo',self.repository,'--clobber',*[str(f) for f in files])

    def download(self,tag,names,folder):
        self.cli('release','download',tag,'--repo',self.repository,'--dir',str(folder),*[part for name in names for part in ('--pattern',name)])

    def publish(self,tag):
        self.cli('release','edit',tag,'--repo',self.repository,'--draft=false','--latest')


def publish(github,tag,commit,files):
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag) or not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise ValueError('リリース識別情報が不正です')
    expected={file.name:file.read_bytes() for file in files}
    if len(expected)!=2 or not any(name.endswith('.zip') for name in expected) or not any(name.endswith('.sha256') for name in expected):
        raise ValueError('リリース成果物一覧が不正です')
    reference=github.tag_commit(tag)
    if reference is not None and reference != commit:
        raise ValueError('同じバージョンのタグが別のコミットを指しています。VERSIONを更新してください')
    current=github.release(tag)
    if current is None:
        github.create_draft(tag,commit)
        current=github.release(tag)
    if current is None:
        raise ValueError('作成したドラフトReleaseを取得できません。再実行前にGitHubの状態を確認してください')
    if current['target_commitish'] != commit and reference != commit:
        raise ValueError('既存リリースの対象コミットが一致しません')
    existing={asset['name'] for asset in current['assets']}
    if existing-set(expected):
        raise ValueError('既存リリースに想定外の成果物があります')
    if current['draft']:
        github.upload(tag,files)
    elif existing != set(expected):
        raise ValueError('公開済みリリースの成果物が不足しています')
    with tempfile.TemporaryDirectory(prefix='jp-release-') as temp:
        github.download(tag,sorted(expected),Path(temp))
        if any((Path(temp)/name).read_bytes()!=data for name,data in expected.items()):
            raise ValueError('アップロードした成果物が一致しません。公開を中止します')
    if current['draft']:
        github.publish(tag)
    return '作成済み' if not current['draft'] else '作成成功'
