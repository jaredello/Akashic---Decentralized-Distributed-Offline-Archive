# Contributing

Thanks for helping! This project aims to be easy to read, so please keep it that way.

## House style
- **One job per file.** If a file does two things, split it. Backend modules are named after what they
  do (`wikipedia_api.py`, `disc_images.py`). Screen sections live in `frontend/src/components/<screen>/`.
- **Start every file with a short plain-English comment** saying what it is for. The Source page shows
  this comment as "What this file does".
- **Plain names over clever ones.** Prefer `fetch_plain_text` to `_fx`, and `intro_html` to `lh`.
- **Small functions.** If you need a comment to explain a block, make it a function with a good name.
- Python: formatted for readability, checked with `ruff`. JavaScript: React function components and hooks.
- Never commit secrets. Settings live in `.env` files, which are never shown or committed.

## Workflow
1. Fork the repo and create a branch.
2. Make your change and add or adjust a test in `backend/tests/` if it changes behaviour.
3. Run `cd backend && pytest`.
4. Open a pull request describing **what** changed and **why**, in plain words.

## Reporting problems
Open an issue with what you did, what you expected and what happened instead. Screenshots help.
