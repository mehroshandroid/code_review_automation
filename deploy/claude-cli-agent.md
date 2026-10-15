# Claude CLI agent on the Linux server

The agent (`claude_cli_agent/`) lets reviews use the `claude` CLI that's logged in on the server as the LLM provider ("Claude CLI (local)" in Settings).

- **Where it runs:** natively on the server under the deploy user, as a systemd service. It isn't in Docker, because it needs that user's `claude` login.
- **How the backend reaches it:** at `http://host.docker.internal:8200`. `docker-compose.prod.yml` maps that name to the host.

**The agent has no authentication.** Anyone who can reach port 8200 can run prompts on the logged-in Claude account. So it listens only on Docker's bridge address (normally `172.17.0.1`), never on the public IP, and the firewall admits only Docker's private range to it.

## Install

```bash
# 1. The claude CLI, then log in (headless: open the printed URL on another machine, paste the code back)
curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude                       # type /login, follow the prompts, then /exit
claude --print "Reply with the word ok"

# 2. The agent's Python environment
sudo apt-get install -y python3-venv
cd /opt/codeassure/claude_cli_agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Docker's bridge address (normally 172.17.0.1)
DOCKER_HOST_IP=$(ip -4 addr show docker0 | grep -oP 'inet \K[\d.]+'); echo $DOCKER_HOST_IP

# 4. The service
sudo tee /etc/systemd/system/claude-cli-agent.service > /dev/null <<EOF
[Unit]
Description=CodeAssure Claude CLI agent
After=network-online.target docker.service
Wants=docker.service
# Restart with Docker: the agent listens on Docker's bridge address, which a Docker restart recreates.
PartOf=docker.service

[Service]
User=$USER
WorkingDirectory=/opt/codeassure/claude_cli_agent
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/codeassure/claude_cli_agent/venv/bin/uvicorn main:app --host $DOCKER_HOST_IP --port 8200
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now claude-cli-agent
systemctl status claude-cli-agent --no-pager | head -5

# 5. Firewall: containers (172.16.0.0/12) may reach the agent; nothing else
sudo ufw allow from 172.16.0.0/12 to $DOCKER_HOST_IP port 8200 proto tcp
```

## Check

```bash
curl -s http://$DOCKER_HOST_IP:8200/health                       # {"status":"ok"} on the server
cd /opt/codeassure && docker compose exec backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8200/health').read())"
```

From any other machine, `curl --max-time 5 http://<server-ip>:8200/health` must **fail**.

## Operating it

| Task | Command |
|---|---|
| Logs | `journalctl -u claude-cli-agent -f` |
| Restart (after `git pull` changes the agent) | `sudo systemctl restart claude-cli-agent` |
| Login expired | Run `claude` as the deploy user, `/login` again, then restart the service |
