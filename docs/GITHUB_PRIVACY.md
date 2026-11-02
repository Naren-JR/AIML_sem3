# GitHub preparation

The repository publishes application code, tests, dependency locks, configuration examples and public-facing methodology. Local inputs remain on disk but are excluded from Git by default:

- Environment files and private-key/credential files.
- Python environments, node_modules, build outputs and editor state.
- Supplied research PDFs and their extracted text.
- Raw/processed telemetry, imported frontend reference exports, track graphics, reports, audit inventories and experiment results.

This default protects internal documents, personal paths and supplied assets whose redistribution permissions have not been established. Ignoring a file does not encrypt it or restrict local access. Do not force-add ignored files without reviewing their contents and redistribution permissions.

## Fresh clone

Install Python dependencies and run npm ci in frontend as described in README. Restore the race input locally at dataPreprocess/rawData/australiar.csv before running the model. To enable optional static references/report panels, restore frontend_unzipped/ and reports/ from your own local copies. Never substitute fabricated data for missing inputs. Real-data tests and reproduction commands require those inputs; a source-only clone is intentionally not a self-contained dataset distribution.

## Before committing

Run `python -m scripts.check_publication` using the project virtual environment. It scans Git's non-ignored tracked/untracked text candidates for common credential signatures and identifying filesystem paths, and checks common sensitive file names. It prints only locations and finding types, not matched secrets. Automated detection is a precaution, not proof that every file is safe. Binary content is not semantically inspected; supplied binary material is ignored by default.

Review `git status --short` and `git diff --cached --stat` after staging. GitHub repository visibility is your choice; a private repository offers additional access control. No remote, commit or push is created by this preparation.

If a credential is ever committed/published, revoke or rotate it; adding an ignore rule afterward does not remove it from history.
