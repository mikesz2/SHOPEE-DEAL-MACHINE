# Security

Do not commit credentials, API keys, Telegram sessions, databases or production backups.

Use `.env.example` only as a template and keep real values in `.env`.

If a secret is accidentally committed, revoke/rotate it immediately and remove it from Git history before publishing the repository.
