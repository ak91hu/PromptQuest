# Publish to GitHub as ak91hu

Destination: **https://github.com/ak91hu/PromptQuest**.

Publication requires an authenticated GitHub CLI connection as ak91hu with write access to the destination repository.

A credential-free release archive is available under outputs/PromptQuest-release.zip after packaging. The exact publication allowlist is deploy/publication-files.json.

## Publish from an authenticated terminal

Use Git and GitHub CLI in a terminal with working GitHub network access. Authenticate as ak91hu using the normal GitHub CLI login flow, then run:

```powershell
.\scripts\publish-github.ps1
```

The script verifies the authenticated account is exactly ak91hu, resolves the repository's default branch, clones it into a new outputs/ directory, copies only allowlisted source files, and makes a normal non-forced commit/push. Commit attribution uses the account's GitHub noreply address.

Before contacting GitHub, it checks the publication allowlist for private files and
credentials. Before committing, it also checks every file in the Git index, including
existing repository files. A failed check stops publication without printing secret
values. Run the local check separately with `python scripts/check-publication.py`.
These checks cover the current contents, not older commits in repository history.

Existing unrelated repository files are retained. Allowlisted paths are replaced by the prepared project versions. Existing repository history is retained; nothing is force-pushed. A protected branch may reject the push, in which case use a branch and pull request under your repository policy.

Empty repositories are supported: the script creates the selected branch for its initial commit.

The archive excludes .env, local credential variants, security ledgers, player data, runtime files, dependency directories, and QA outputs. .env.example is included with empty credentials. Never upload the working directory indiscriminately.

After publication, connect Northflank to this repository and finish the account-specific setup in [NORTHFLANK.md](NORTHFLANK.md).
