"""Folder-sync tests use temporary local Git repositories, never Overleaf."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]/"tools"
sys.path.insert(0,str(TOOLS))
from overleaf_sync import OverleafSync,SyncError,PROJECT_ID,validate_remote


def git(*args,cwd=None):
    env=os.environ.copy();env["GIT_CONFIG_NOSYSTEM"]="1"
    result=subprocess.run(["git","-c","user.name=Sync Test","-c","user.email=sync-test@example.invalid",*map(str,args)],
                          cwd=cwd,env=env,text=True,capture_output=True)
    if result.returncode:raise AssertionError(result.stderr)
    return result.stdout.strip()


class FolderSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.root=self.base/"parent/HW09";self.source=self.root/"overleaf"
        self.seed=self.base/"seed";self.seed.mkdir()
        git("init","-b","main",self.seed)
        (self.seed/"main.tex").write_text("original\n");(self.seed/".gitignore").write_text("*.aux\n")
        git("add",".",cwd=self.seed);git("commit","-m","Original",cwd=self.seed)
        self.remote=self.base/"remote.git";git("clone","--bare",self.seed,self.remote)
        self.source.mkdir(parents=True)
        for name in ("main.tex",".gitignore"):(self.source/name).write_bytes((self.seed/name).read_bytes())
        self.sync=OverleafSync(self.root);self.sync.gitdir.parent.mkdir()
        git("clone","--bare",self.remote,self.sync.gitdir)
        args=["--git-dir="+str(self.sync.gitdir),"--work-tree="+str(self.source)]
        self.args=args
        git(*args,"config","core.bare","false")
        git(*args,"config","core.worktree",self.source)
        url="https://git@git.overleaf.com/"+PROJECT_ID
        git(*args,"config","remote.origin.url",url)
        git(*args,"config","url."+self.remote.as_uri()+".insteadOf",url)
        git(*args,"config","remote.origin.fetch","refs/heads/*:refs/remotes/origin/*")
        git(*args,"update-ref","refs/remotes/origin/main","HEAD")
        git(*args,"config","branch.main.remote","origin")
        git(*args,"config","branch.main.merge","refs/heads/main")
        git(*args,"config","user.name","Sync Test");git(*args,"config","user.email","sync-test@example.invalid")
        git(*args,"read-tree","HEAD")

    def tearDown(self):self.tmp.cleanup()

    def remote_change(self,text):
        (self.seed/"main.tex").write_text(text)
        git("add",".",cwd=self.seed);git("commit","-m","Remote edit",cwd=self.seed)
        git("push",self.remote,"main",cwd=self.seed)

    def test_plain_parent_tracking_without_nested_metadata(self):
        parent=self.root.parent;git("init",parent)
        (parent/".gitignore").write_text(".local/\n")
        git("add",".",cwd=parent)
        listing=git("ls-files","--stage",cwd=parent)
        self.assertIn("100644",listing);self.assertIn("HW09/overleaf/main.tex",listing)
        self.assertNotIn("160000",listing);self.assertNotIn("overleaf-git",listing)
        self.assertFalse((self.source/".git").exists())
        with patch.object(self.sync,"refresh") as fetch:
            self.assertFalse(self.sync.status()["changes"]);fetch.assert_not_called()

    def test_clean_pull_fast_forwards_only_source(self):
        outside=self.root/"keep.txt";outside.write_text("unchanged")
        self.remote_change("remote update\n")
        result=self.sync.pull()
        self.assertEqual((self.source/"main.tex").read_text(),"remote update\n")
        self.assertEqual(outside.read_text(),"unchanged");self.assertFalse(result["changes"])

    def test_dirty_pull_refuses_before_fetch(self):
        (self.source/"main.tex").write_text("local edit\n")
        with patch.object(self.sync,"refresh") as fetch:
            with self.assertRaisesRegex(SyncError,"Local source folder has changes"):self.sync.pull()
            fetch.assert_not_called()
        self.assertEqual((self.source/"main.tex").read_text(),"local edit\n")

    def test_manual_push_commits_only_this_folder(self):
        outside=self.root/"private.txt";outside.write_text("outside source")
        (self.source/"main.tex").write_text("local update\n")
        result=self.sync.push("Reviewed source update")
        self.assertEqual(git("--git-dir="+str(self.remote),"show","main:main.tex"),"local update")
        self.assertNotIn("private.txt",git("--git-dir="+str(self.remote),"ls-tree","-r","--name-only","main"))
        self.assertFalse(result["changes"]);self.assertEqual(result["ahead"],0)

    def test_remote_edits_block_push_without_staging_local_changes(self):
        self.remote_change("Overleaf edit\n")
        (self.source/"main.tex").write_text("local edit\n")
        with self.assertRaisesRegex(SyncError,"Overleaf has new commits"):self.sync.push("Must not commit")
        self.assertEqual((self.source/"main.tex").read_text(),"local edit\n")
        self.assertFalse(git(*self.args,"diff","--cached","--name-only"))

    def test_divergent_commits_block_pull(self):
        (self.source/"main.tex").write_text("local commit\n")
        git(*self.args,"add",".");git(*self.args,"commit","-m","Local commit")
        head=git(*self.args,"rev-parse","HEAD")
        self.remote_change("remote commit\n")
        with self.assertRaisesRegex(SyncError,"diverged"):self.sync.pull()
        self.assertEqual(git(*self.args,"rev-parse","HEAD"),head)
        self.assertEqual((self.source/"main.tex").read_text(),"local commit\n")

    def test_ignored_local_file_is_not_overwritten(self):
        (self.source/"main.aux").write_text("preserve local scratch")
        (self.seed/"main.aux").write_text("remote file")
        git("add","-f","main.aux",cwd=self.seed);git("commit","-m","Remote addition",cwd=self.seed)
        git("push",self.remote,"main",cwd=self.seed)
        with self.assertRaises(SyncError):self.sync.pull()
        self.assertEqual((self.source/"main.aux").read_text(),"preserve local scratch")

    def test_secrets_and_symlinks_refused_without_network(self):
        (self.source/".env").write_text("private")
        with patch.object(self.sync,"refresh") as fetch:
            with self.assertRaisesRegex(SyncError,"Credential-like file"):self.sync.push("No")
            fetch.assert_not_called()
        (self.source/".env").unlink();(self.source/"linked.tex").symlink_to(self.seed/"main.tex")
        with self.assertRaisesRegex(SyncError,"symbolic links"):self.sync.status()

    def test_wrong_project_password_urls_and_nested_git_refused(self):
        for url in ("https://git.overleaf.com/wrong","https://git:secret@git.overleaf.com/"+PROJECT_ID):
            with self.assertRaises(SyncError):validate_remote(url)
        (self.source/".git").write_text("gitdir: elsewhere")
        with self.assertRaisesRegex(SyncError,"nested .git"):self.sync.status()


if __name__=="__main__":unittest.main()
