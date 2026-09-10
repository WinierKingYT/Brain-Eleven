---
type: decision
title: Git Emergency Recovery - Lost Commits and Branches
category: Security & DevOps
status: active
created: 2026-08-27
source: k88hudson/git-flight-rules (Hamle 4)
tags: [git, recovery, emergency, devops]
---

# Git Emergency Recovery

**Pattern:** Undo Mistakes at Any Level

## Lost Commits

```
Accidentally deleted branch? (git branch -D main)

Recovery:
  git reflog  # Shows all HEAD movements
  → find commit hash from delete: "reset: moving to xyz"
  git checkout -b main abc123  # Restore at that point
```

## Accidental Force Push

```
Pushed --force, rewrote team's history?

git reflog origin/main  # On remote? Ask for their reflog
git push -f origin abc123:main  # Restore from local reflog

Prevention: Protect main branch (no force push allowed)
```

## Uncommitted Work Lost

```
Had code, switched branch, lost changes?

git reflog  # Find dangling commits
git fsck --lost-found  # Find orphaned commits
ls .git/lost-found/commits/  # Browse them
git show abc123  # Inspect content
```

## Wrong Commit Message

```
Last commit message is typo

git commit --amend -m "Correct message"  # Not pushed
git push -f origin main  # Pushed (only if not shared)

Shared branch: Don't amend. Create new commit:
  git revert abc123  # Undo last commit
  git commit -m "Fix previous message"
```

## Merge Conflict Resolution

```
git merge feature ← CONFLICT

Options:
1. Abort: git merge --abort (start over)
2. Resolve: edit files, git add, git commit
3. Ours: git checkout --ours file.js (keep current)
4. Theirs: git checkout --theirs file.js (take incoming)
```

---

**Bağlantılar:** [[hamle4-011-incident-response-playbook]]
