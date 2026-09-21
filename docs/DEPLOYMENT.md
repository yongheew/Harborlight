# Deploy Harborlight

The local app is verified; this document is deployment configuration, not evidence of a completed cloud deployment.

## Render Docker service

1. Create a repository containing this project. Exclude `.env`, `var/`, virtual environments, real shipment records and organizer answer keys. Include the original fictional `demo/` files.
2. In your Render account create a Blueprint from that repository and inspect `render.yaml`. It requests a paid single-instance Docker service with a 1 GB persistent disk at `/app/var`. Confirm current costs before creating it.
3. Render supplies `PORT`; the Docker image binds on `0.0.0.0` and starts `python run.py`. `/api/health` is the health check.
4. Set `OPENAI_API_KEY` only if cloud-assisted processing will be demonstrated. Keep `OPENAI_MODEL` configurable. For local-AI-only operation leave the key empty; meaningful cloud infrastructure can still be the hosted application itself.
5. Find the generated `HARBORLIGHT_PASSWORD` in your service environment and provide the `judge` username/password to the judging team through the approved submission channel. Do not publish credentials in the repository. For an intentionally public synthetic-only demo, separately decide access policy; the supplied blueprint keeps writes protected.
6. After deployment, load the public HTTPS URL, verify all demo cases, upload a participant-only sample, save/reload a review, retry original sources, download all three exports, and check `/api/health` and `/api/audit`. Restart the service and confirm review persistence before submission.
7. Record the deployed URL and tested commit in the submission and validation notes. Keep the service available during judging.

Render's default service filesystem is ephemeral; the persistent disk is required to retain this SQLite implementation through restarts/redeploys. Only a single service instance should use this file database. Scaling requires moving persistence to a shared database and attachments to object storage.

Official references: [FastAPI deployment](https://render.com/docs/deploy-fastapi), [Blueprint configuration](https://render.com/docs/blueprint-spec), [persistent disks](https://render.com/docs/disks). OpenAI's [structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) documents the optional cloud request format. Current pricing/account availability must be checked when deploying.

## Alternate cloud provider

Deploy the supplied Dockerfile to a container service supporting a persistent writable volume. Supply `HOST=0.0.0.0`, the assigned `PORT`, a data directory on that volume, and access credentials. Terminate TLS at the platform. Do not simply upload this as a static website; the Python API and SQLite storage are required.

## Local data and backups

The database is `HARBORLIGHT_DATA_DIR/harborlight.sqlite3`. Stop the app before copying the entire data directory as a simple backup, or use SQLite's online backup API for live backups. Preserve the database and any WAL files together if not using the backup API. Never delete a data volume to fix an import error. Re-import source records or use the retry workflow instead.
