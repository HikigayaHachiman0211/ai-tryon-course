# Security and privacy notes

## Do not commit

- API keys, access tokens, JWT/Fernet/ingest secrets or database passwords
- `.env` files other than documented `.env.example` templates
- Google Cloud service-account JSON, private keys or local credential caches
- local databases, logs, uploaded photos, generated images or request histories
- real Cloud project IDs, bucket names, service URLs or private network addresses

Use environment variables and a managed secret store for deployments. Rotate a credential immediately if it is ever committed, even if the commit is later deleted.

## User images

Full-body photos and virtual try-on results can identify a person. A public deployment should provide explicit consent and retention notices, use authenticated storage, minimize logging, enforce deletion windows, and restrict administrator access. The included cleanup settings are an implementation aid, not a complete privacy program.

## Production checks

The administrator service refuses production startup when critical secrets are missing or weak. Production deployments should additionally use HTTPS, restricted CORS origins, least-privilege cloud identities, private database connectivity, rate limits, monitoring and regular dependency updates.

## Reporting a vulnerability

Open a private GitHub security advisory for the repository instead of posting credentials or exploit details in a public issue.
