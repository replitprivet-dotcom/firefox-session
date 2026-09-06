# Firefox Session Gateway

This repository deploys an isolated Firefox session gateway with a FastAPI management API. Each session ID receives a separate Firefox container, persistent profile volume, web port, VNC port, tokenized access URL, and expiration time.

## One-command VPS setup

Clone the repository on the VPS and run the installer as root:

```bash
git clone https://github.com/replitprivet-dotcom/firefox-session.git /opt/firefox-session
cd /opt/firefox-session
sudo bash setup.sh
```

The script installs Docker and `cloudflared`, builds and starts the gateway, then asks whether Cloudflare should be configured. If enabled, it prints a Cloudflare authorization URL, asks for the root domain and desired subdomain, creates the tunnel, configures DNS, and starts the tunnel as a service.

For example, if the root domain is `example.com` and the requested subdomain is `firefox`, the resulting URL is `https://firefox.example.com/`.

## API

The management key is required for all management operations:

```text
/adduser?password=abcd&day=7&id=newuser&key=maha7788
/newpas?id=newuser&password=abcd&newpassword=wxyz&key=maha7788
/delete?id=newuser&password=wxyz&key=maha7788
```

The generated Firefox URL is returned by `/adduser`. The root web login at `/` accepts the session ID as the username and the session password as the password, then redirects to that Firefox session.

## Security

Change `ADMIN_KEY` before production use. Do not commit tokens, Cloudflare credentials, or session passwords. A GitHub token should be revoked and regenerated if it was pasted into a chat or shell where it may have been logged.
