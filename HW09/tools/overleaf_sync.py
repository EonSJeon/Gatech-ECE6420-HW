#!/usr/bin/env python3
"""Manually sync only HW09/overleaf with its existing Overleaf Git project.

Git metadata stays in ignored HW09/.local/overleaf-git. No nested .git file,
automatic sync, credentials storage, simulation, or LaTeX compilation is used.
Initial remote attachment is a separate explicit setup step documented in the
source-folder README. Status never contacts the network unless --refresh is set.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
PROJECT_ID="6af68c3c1b2af4608fb66bfd"
SECRET=re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-proj-|sk-)[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[A-Z0-9]{16}\b|\bxox[baprs]-[A-Za-z0-9-]{20,}")


class SyncError(RuntimeError):
    pass


def safe_error(value):
    """Do not echo credential-bearing URLs or recognizable tokens from Git."""
    value=re.sub(r"(https?://)[^\s/@]+(?::[^\s/@]*)?@",r"\1[redacted]@",value)
    return SECRET.sub(b"[redacted]",value.encode()).decode(errors="replace").strip()


def validate_remote(value):
    url=urlsplit(value)
    if (url.scheme!="https" or url.hostname!="git.overleaf.com" or url.port not in {None,443}
        or url.username not in {None,"git"} or url.password is not None
        or url.path.rstrip("/")!="/"+PROJECT_ID or url.query or url.fragment
        or any(c.isspace() for c in value)):
        raise SyncError("The origin must be the confirmed HTTPS Git URL for this Overleaf project, without a password/token in the URL")
    return value


class OverleafSync:
    def __init__(self,root=ROOT):
        self.root=Path(root).resolve()
        self.source=self.root/"overleaf"
        self.gitdir=self.root/".local/overleaf-git"

    def git(self,*args,check=True):
        env=os.environ.copy()
        for key in ("GIT_DIR","GIT_WORK_TREE","GIT_INDEX_FILE","GIT_COMMON_DIR",
                    "GIT_OBJECT_DIRECTORY","GIT_ALTERNATE_OBJECT_DIRECTORIES","GIT_NAMESPACE"):
            env.pop(key,None)
        env["GIT_TERMINAL_PROMPT"]="0"
        command=["git","-c","credential.helper=","-c","credential.helper=osxkeychain",
                 "-c","core.hooksPath=/dev/null","-c","merge.autoStash=false",
                 "--git-dir="+str(self.gitdir),"--work-tree="+str(self.source),*args]
        result=subprocess.run(command,cwd=self.source,env=env,text=True,capture_output=True)
        if check and result.returncode:
            raise SyncError("Git "+args[0]+" failed: "+safe_error(result.stderr or result.stdout))
        return result

    def guard(self):
        if not self.source.is_dir() or self.source.is_symlink():
            raise SyncError("The maintained overleaf folder is missing or is a symbolic link")
        if self.gitdir.is_symlink() or (self.root/".local").is_symlink() or not self.gitdir.is_dir():
            raise SyncError("Attach the confirmed remote to ignored .local/overleaf-git first; do not create overleaf/.git")
        for path in self.source.rglob("*"):
            if path.is_symlink() or path.name==".git":
                raise SyncError("The source folder must contain regular source files, without symbolic links or nested .git metadata")
        if self.git("rev-parse","--is-bare-repository").stdout.strip()!="false":
            raise SyncError("The metadata must be attached as a non-bare repository without checking out files")
        configured=self.git("config","--path","--get","core.worktree").stdout.strip()
        if not configured or Path(configured).resolve()!=self.source:
            raise SyncError("Git core.worktree does not identify the maintained HW09/overleaf folder")
        if not (self.gitdir/"index").is_file():
            raise SyncError("Initialize the separate index with read-tree HEAD; do not check out over the maintained folder")
        for name in ("index.lock","MERGE_HEAD","CHERRY_PICK_HEAD","REBASE_HEAD","rebase-merge","rebase-apply"):
            if (self.gitdir/name).exists():raise SyncError("Finish the existing Git operation before syncing: "+name)
        validate_remote(self.git("config","--get","remote.origin.url").stdout.strip())
        push_url=self.git("config","--get","remote.origin.pushurl",check=False)
        if push_url.returncode==0:validate_remote(push_url.stdout.strip())
        branch=self.git("symbolic-ref","--quiet","--short","HEAD").stdout.strip()
        if not branch:raise SyncError("Detached Git HEAD cannot be synced")
        remote=self.git("config","--get","branch."+branch+".remote").stdout.strip()
        merge=self.git("config","--get","branch."+branch+".merge").stdout.strip()
        if remote!="origin" or merge!="refs/heads/"+branch:
            raise SyncError("The current branch must track the same named origin branch")
        self.git("rev-parse","--verify","refs/remotes/origin/"+branch)
        return branch

    def changes(self):
        return [row for row in self.git("status","--porcelain=v1","-z","--untracked-files=all").stdout.split("\0") if row]

    def relation(self,branch):
        counts=self.git("rev-list","--left-right","--count","HEAD...refs/remotes/origin/"+branch).stdout.split()
        return int(counts[0]),int(counts[1])

    def refresh(self,branch):
        # No force refspec: a rewritten remote history is also refused.
        self.git("fetch","--no-tags","origin","refs/heads/"+branch+":refs/remotes/origin/"+branch)

    def scan_source(self):
        names=set(self.git("ls-files","-c","-o","--exclude-standard","-z").stdout.split("\0"))-{ "" }
        for name in names:
            path=self.source/name
            if path.name in {".env",".remote.env",".gitconfig","id_rsa","id_ed25519"} or path.suffix in {".key",".pem"}:
                raise SyncError("Credential-like file in source folder; no changes staged or pushed")
            if path.exists() and (not path.is_file() or not path.resolve().is_relative_to(self.source)):
                raise SyncError("Unsafe file in source folder; no changes staged or pushed")
            if path.is_file() and SECRET.search(path.read_bytes()):
                raise SyncError("Credential-like source content found; no changes staged or pushed")

    def status(self,refresh=False):
        branch=self.guard()
        if refresh:self.refresh(branch)
        ahead,behind=self.relation(branch)
        return {"project":"https://www.overleaf.com/project/"+PROJECT_ID,
                "source":str(self.source),"git_metadata":str(self.gitdir),"branch":branch,
                "ahead":ahead,"behind":behind,"remote_refreshed":refresh,
                "changes":self.changes(),"automatic_sync":False}

    def pull(self):
        branch=self.guard()
        if self.changes():raise SyncError("Local source folder has changes. Preserve/review them before pull; nothing was fetched or overwritten")
        self.refresh(branch)
        ahead,behind=self.relation(branch)
        if ahead and behind:raise SyncError("Local and Overleaf commits diverged. Resolve explicitly with normal Git; no merge or overwrite was attempted")
        if behind:self.git("merge","--ff-only","--no-edit","--no-stat","--no-overwrite-ignore","refs/remotes/origin/"+branch)
        return self.status()

    def push(self,message=None):
        branch=self.guard();self.scan_source()
        self.refresh(branch)
        _,behind=self.relation(branch)
        if behind:raise SyncError("Overleaf has new commits. Pull/reconcile them before push; local changes were not staged, committed, or overwritten")
        if self.changes():
            if not message or not message.strip():raise SyncError("Review local source changes, then pass --message to commit this folder before manual push")
            self.git("add","--all","--",".")
            self.git("commit","--message",message)
        ahead,_=self.relation(branch)
        if ahead:self.git("push","origin","HEAD:refs/heads/"+branch)
        return self.status()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("status","pull","push"))
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--refresh",action="store_true",help="Refresh cached remote state for status; contacts Overleaf")
    parser.add_argument("-m","--message",help="Explicit commit message for local source changes before manual push")
    args=parser.parse_args()
    if args.refresh and args.command!="status":parser.error("--refresh applies only to status")
    if args.message and args.command!="push":parser.error("--message applies only to push")
    sync=OverleafSync(args.root)
    try:
        result=sync.status(args.refresh) if args.command=="status" else sync.pull() if args.command=="pull" else sync.push(args.message)
    except (SyncError,ValueError) as exc:
        parser.exit(1,safe_error(str(exc))+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
