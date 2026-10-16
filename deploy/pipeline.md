# Deployment pipeline (Azure Pipelines)

`azure-pipelines.yml` runs the tests on every pull request to `master`. When something is merged to `master`:

1. **Test:** the backend and frontend tests run on Microsoft-hosted agents.
2. **Approve:** the run pauses until an approver accepts it in Azure DevOps.
3. **Deploy:** an agent installed on the server does the update:
    - fast-forwards `/opt/codeassure` to exactly the approved commit;
    - rebuilds and restarts the containers;
    - waits for the health check;
    - prunes old images.

    Database migrations run automatically when the backend starts.

The code lives in Azure Repos. The deploy step fetches it with the run's own short-lived token (`System.AccessToken`), so the server stores no Git credentials. `/opt/codeassure` only needs its `origin` remote pointing at the Azure Repos URL.

## One-time setup

### 1. Create the pipeline

In Azure DevOps, go to **Pipelines → New pipeline → Azure Repos Git**, then pick the repo, then **Existing Azure Pipelines YAML file → `/azure-pipelines.yml`**. **Save**; don't run yet.

On the server, point the clone at Azure Repos once. This is only used for display: fetches use the pipeline's token.

```bash
cd /opt/codeassure && git remote set-url origin https://dev.azure.com/<org>/<project>/_git/<repo>
```

### 2. The environment and its approvers

1. Go to **Pipelines → Environments → New environment**, name it `codeassure-production`, with resource **None**.
2. Open it, then **⋯ → Approvals and checks → + → Approvals**.
3. Add the approvers (people or a group). Leave **"Allow approvers to approve their own runs"** unticked if the person who merged must not approve their own deployment.
4. Set the timeout, for example 3 days. After that, an unapproved run is cancelled.

### 3. The agent on the server

1. Go to **Project settings → Agent pools → Add pool**: type **Self-hosted**, name `codeassure-server`, and tick **Grant access permission to all pipelines**.
2. In the pool, click **New agent → Linux** and copy the download link.
3. Create a **Personal Access Token** with scope **Agent Pools (Read & manage)**. It's used only once, to register the agent.
4. On the server, as the deploy user (`teoai`, which is in the `docker` group):

```bash
mkdir -p ~/azagent && cd ~/azagent
curl -fsSL -o agent.tar.gz '<download link from the New agent dialog>'
tar -xzf agent.tar.gz
./config.sh --unattended --url https://dev.azure.com/<org> --auth pat --token '<PAT>' \
  --pool codeassure-server --agent "$(hostname)" --acceptTeeEula
sudo ./svc.sh install $USER
sudo ./svc.sh start
sudo ./svc.sh status
```

The agent makes **outbound** HTTPS connections to Azure DevOps only. No port is opened on the server.

### 4. Protect `master`

So that every change goes through a reviewed pull request and passes the tests, go to **Repos → Branches → `master` → ⋯ → Branch policies** and set:

- **Require a minimum number of reviewers:** 1. Untick "Allow requestors to approve their own changes" if needed.
- **Build validation:** add this pipeline, with the trigger set to Automatic and the policy Required.

Once a policy is on, nobody can push to `master` directly. Every change is a pull request.

## Day to day

- **Merge a pull request to `master`.** The pipeline tests it, then waits. The approver gets an email from Azure DevOps and clicks **Review → Approve**, and the server updates in a few minutes. The first build after a compiler change takes longer.
- **If the health check fails,** the run fails and its log shows the backend's last 80 log lines. The previous containers have already been replaced, so fix forward, or check out the previous commit on the server and run `docker compose up -d --build`.
- **If `claude_cli_agent/` changed,** the run prints a warning: run `sudo systemctl restart claude-cli-agent` on the server.
- **If the server's copy was edited by hand,** the fast-forward refuses to deploy. Check `git status` in `/opt/codeassure`; `.env` is untracked and never touched.
