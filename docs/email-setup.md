# Email setup (CodeAssure workflow emails)

CodeAssure sends workflow emails, for example:
- review started
- reviewer assigned
- review ready
- review failed
- review finalized
- reminders

Until it's configured, it runs in **log mode**, where emails only appear in the server log and nothing is sent. Setting it up takes two steps: the network team provides a mailbox and credentials, then you put those settings in the project's `.env` file. That file sits next to `docker-compose.yml` and is excluded from git, so secrets are never committed.

## 1. What to ask the network team

You need a sender mailbox, for example `codeassure@teo-intl.com`. A shared mailbox is fine and needs no licence. You also need **one** of the two options below.

### Option A: Microsoft Graph (recommended)

- An Entra ID app registration with the **application** permission **`Mail.Send`**, with admin consent granted.
- An Exchange Online **Application Access Policy** (or RBAC for Applications) that restricts the app to **only** the CodeAssure mailbox.
- They provide:
  - tenant ID
  - client ID
  - client secret, and its expiry date
  - sender address
- If they grant `Mail.Send` to the **existing Microsoft sign-in app**, no new IDs are needed. CodeAssure falls back to the sign-in app's `AZURE_AD_*` settings.

### Option B: SMTP

- SMTP AUTH enabled on the mailbox, and confirmation that basic-auth SMTP is still allowed in the tenant. Microsoft has been retiring basic-auth SMTP.
- They provide:
  - host (`smtp.office365.com`)
  - port **587** (STARTTLS)
  - username
  - password
- Port 465 (implicit TLS) is **not** supported.

## 2. Configure CodeAssure

Add **one** of these blocks to `.env` in the project root.

**Graph:**

```env
EMAIL_MODE=graph
EMAIL_FROM=codeassure@teo-intl.com
EMAIL_FROM_NAME=CodeAssure
GRAPH_TENANT_ID=<tenant id>
GRAPH_CLIENT_ID=<client id>
GRAPH_CLIENT_SECRET=<client secret>
# Leave out the three GRAPH_* lines if Mail.Send was granted to the existing sign-in app
```

**SMTP:**

```env
EMAIL_MODE=smtp
EMAIL_FROM=codeassure@teo-intl.com
EMAIL_FROM_NAME=CodeAssure
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=codeassure@teo-intl.com
SMTP_PASSWORD=<password>
SMTP_STARTTLS=true
```

Restart the backend so it picks up the settings:

```bash
docker compose up -d --no-deps backend
```

## 3. Verify

1. Open **Settings → Email** as an admin. The delivery mode should read *Microsoft Graph* or *SMTP*, followed by **"Configured."** If something is missing, the exact variable name is listed there.
2. Click **Send test email**. It should arrive within a few seconds and show as **sent** in the list. If it shows **failed**, the error explains why, for example a wrong secret or SMTP AUTH being disabled.
3. Rely on it only after the test email arrives. A broken setup makes every pending email fail within about 30 minutes, and **Retry** works one email at a time.

## Before production

The links inside emails come from `FRONTEND_BASE_URL`. It is currently **hard-coded to `http://localhost:3000`** in `docker-compose.yml`, not read from `.env`. For a real deployment it must point at the production address, otherwise every email links to localhost.

## How it behaves

- **Delivery:** emails are sent in the background within about 15 seconds. Reminders and test emails go out within seconds.
- **Retries:** a failed email is retried with a growing delay, and after 5 attempts it is marked **failed**. You can retry it from Settings → Email.
- **Deactivated users** never receive email.
- **Turning sending on later is safe.** Emails recorded before email delivery existed were marked **skipped** and will never be sent. Emails handled in log mode count as delivered and aren't resent when you switch to Graph or SMTP.
