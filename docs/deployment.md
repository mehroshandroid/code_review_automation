# Deploying CodeAssure on a server

CodeAssure runs on one Ubuntu server with Docker Compose. The production setup is `docker-compose.yml` plus `docker-compose.prod.yml`.

- **Public:** only nginx (port 80) is published. It serves the app at `/` and forwards `/api` to the backend.
- **Private:** the backend, the database and the compilers are reachable inside Docker only.

## Server layout

| What | Where |
|---|---|
| Code | `/opt/codeassure`, a git clone using a read-only GitHub deploy key (`~/.ssh/codeassure_deploy`) |
| Settings and secrets | `/opt/codeassure/.env`, started from `deploy/env.example`, `chmod 600`, never committed |
| Backups | `/var/backups/codeassure`, written nightly by `deploy/backup.sh` |

`.env` contains `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`, so a plain `docker compose …` uses the production settings.

**Keep a copy of `.env` in a password manager.** It holds the database password and the key that encrypts the stored DevOps PAT.

## First install

1. **Install Docker** Engine and the Compose plugin from Docker's apt repository. Add the user to the `docker` group.
2. **Clone the repo** into `/opt/codeassure`.
3. **Create `.env`:** `cp deploy/env.example .env` and fill it in. The file shows how to generate each secret.
4. **Build and start:** `docker compose build`, then `docker compose up -d`. Database migrations run automatically when the backend starts.
5. **Firewall:** `ufw allow OpenSSH`, `ufw allow 80/tcp`, `ufw allow 443/tcp`, then `ufw enable`.
6. **Log in** with `ADMIN_EMAIL` and `ADMIN_PASSWORD`. Then set the DevOps PAT, the compile checks, the LLM provider and email in Settings.

## Updating to a new version

```bash
cd /opt/codeassure
git pull
docker compose up -d --build
docker compose ps
curl -s localhost/api/health
```

## Backups

`deploy/backup.sh` takes:

- the database, as a `pg_dump` custom-format file;
- the review workbooks and sample templates, as a `.tgz` archive.

It keeps 14 days of backups. Install it once:

```bash
sudo mkdir -p /var/backups/codeassure && sudo chown $USER:$USER /var/backups/codeassure
/opt/codeassure/deploy/backup.sh          # run it once by hand to check
crontab -e                                 # then add the line below
30 2 * * * /opt/codeassure/deploy/backup.sh >> $HOME/codeassure-backup.log 2>&1
```

A backup that stays on the same server doesn't survive losing that server. Copy `/var/backups/codeassure` somewhere else regularly.

**Restore steps** are in the header of `deploy/backup.sh`.

## Useful commands

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Backend logs | `docker compose logs -f --tail 100 backend` |
| Restart one service | `docker compose restart backend` |
| Database browser (over SSH) | `docker compose --profile tools up -d adminer`, then `ssh -L 8080:localhost:8080 <server>` and open http://localhost:8080 |
| Free old images | `docker image prune -f` |

## Not yet done

- **HTTPS and Microsoft sign-in** need a DNS name pointing at the server. Then add TLS to nginx, and set `PUBLIC_URL=https://…` and `COOKIE_SECURE=true`.
- **iOS compile checks** need a Mac build agent. Until then, iOS reviews use static analysis.
- **The Azure DevOps pipeline** isn't set up yet. It will run the tests on merge to master, wait for approval, then deploy.
