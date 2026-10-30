---
name: commit-msg
description: Update the docs for the staged changes, write a conventional commit message and commit. Use when the user says "write a commit message", "generate a commit", "commit my changes", or runs /commit-msg.
---

# Commit the staged changes

1. **Check what is staged.** Run `git diff --staged --stat`. If it prints nothing, stop and tell the
   user to stage their changes first (`git add …`). Don't stage code yourself.
2. **Read the staged diff** with `git diff --staged`. Only staged changes count; ignore unstaged
   and untracked files.
3. **Update the docs to match the staged changes, and stage them.**
   - Check `README.md` (what it does, install, run, tests, project structure, "Status and next
     steps") and `.claude/` (`CLAUDE.md`, `rules/*.md`, skills and agents that describe the changed
     code) against the diff. Edit only what the staged change makes wrong or incomplete.
   - Before editing a doc, run `git diff --name-only -- <file>`. If it already has unstaged edits,
     don't touch it: `git add` would put the user's unrelated edits into this commit. List it and
     ask the user how to proceed.
   - `git add` only the doc files you edited. Never stage other files.
   - If nothing needed updating, say so.
4. **Write the message** from the full staged diff (including the doc updates) in this format:

   ```
   type(scope): short subject

   - what changed
   - why
   ```

   - `type`: one of `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`.
   - `scope`: the area touched, e.g. `verify`, `sources`, `dedup`, `rank`, `scoring`, `report`,
     `cli`, `health`, `config`, `schedule`, `skills`, `agents`. Leave it out (`type: subject`) if
     the change spans many areas. Doc updates made in step 3 don't change the type.
   - Subject: imperative, lowercase, no trailing period, under 60 characters.
   - Body bullets are optional but encouraged: what changed, and why.
   - Never add a `Co-Authored-By` trailer or any other attribution line.
5. **Commit** with the message passed through a heredoc, so the bullets keep their line breaks:

   ```bash
   git commit -F - <<'EOF'
   type(scope): short subject

   - what changed
   - why
   EOF
   ```

   Then show `git log -1 --stat` and list the docs you updated in step 3. Never push.
