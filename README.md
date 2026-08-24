# Spook Shack Discord

Spook Shack Discord is a Discord-based threat-intelligence bot for the Spook Shack ecosystem. It aggregates threat feeds, monitors breach and paste sources, generates dossiers and takedown templates, and posts summarized intelligence into Discord channels.

## What it does

- Polls MISP feeds and routes posts by tag
- Watches ransomware.live for recent victim claims
- Monitors Have I Been Pwned targets
- Pulls the latest NVD CVEs
- Ingests Telegram breach posts
- Scans nginx access logs for suspicious crawl activity
- Generates actor dossiers, weekly reports, and takedown templates
- Dorks paste sites and alerts on new hits
- Searches Shodan from a dedicated Discord channel

## Commands

- `!haunt add email someone@example.com`
- `!haunt add domain example.com`
- `!haunt quick email someone@example.com`
- `!haunt list`
- `!paste add <keyword>`
- `!paste quick <keyword>`
- `!shodan <query>`
- `!shodan count <query>`
- `!shodan info`
- `!actor <name>`
- `!takedown <malicious-domain> <legit-domain>`
- `!weeklyreport #channel`

## Docker deployment

### Local compose

```bash
docker compose up -d --build
```

### Hostinger Docker Manager with GHCR

This repo publishes a container image to GitHub Container Registry (GHCR) from the `main` branch and tagged releases.

Use this image in Hostinger Docker Manager:

```text
ghcr.io/pdpablo/spook-shack-discord:latest
```

1. Open **hPanel → VPS → Manage → Docker Manager**.
2. Create a new project with **Compose manually** or **Compose from URL**.
3. Use the contents of `docker-compose.hostinger.yml`.
4. Add your environment variables in the panel or via `.env`.
5. Deploy the project.

If Hostinger cannot pull the image, make the GHCR package **public** in GitHub Package settings.

### Environment file

Copy `.env.example` to `.env` and fill in your Discord token, API keys, Telegram values, and channel IDs.

### Persisted data

The container stores SQLite databases and JSON state under `/data`. The compose file mounts a named volume there by default.

## Notes for Hostinger VPS

- The GHCR compose file uses a single app service and a persistent volume, which is compatible with Hostinger Docker Manager.
- The bot binds to Discord only; there is no HTTP server to expose.
- Keep `KAMANOSUKE_HOME=/data` so the state files and SQLite databases survive container restarts.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
