#!/usr/bin/env bash
set -Eeuo pipefail

# Firefox Session Gateway + optional Cloudflare Tunnel installer.
# Run as root on the VPS: bash setup.sh

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash setup.sh" >&2
  exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/firefox-gateway}"
PUBLIC_IP="${PUBLIC_IP:-$(curl -4fsS --max-time 10 https://api.ipify.org || true)}"
PUBLIC_IP="${PUBLIC_IP:-172.232.172.170}"
ADMIN_KEY="${ADMIN_KEY:-maha7788}"

apt-get update
apt-get install -y ca-certificates curl docker.io git
systemctl enable --now docker

if ! command -v cloudflared >/dev/null 2>&1; then
  ARCH="$(dpkg --print-architecture)"
  case "$ARCH" in
    amd64) CF_ARCH=amd64 ;;
    arm64) CF_ARCH=arm64 ;;
    *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
  esac
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" -o /usr/local/bin/cloudflared
  chmod 0755 /usr/local/bin/cloudflared
fi

mkdir -p "$REPO_DIR"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cp "$SCRIPT_DIR/firefox_gateway.py" "$REPO_DIR/firefox_gateway.py"
cp "$SCRIPT_DIR/gateway.Dockerfile" "$REPO_DIR/gateway.Dockerfile"

cd "$REPO_DIR"
docker build -t firefox-gateway:local -f gateway.Dockerfile .
docker rm -f firefox-gateway >/dev/null 2>&1 || true
docker run -d --name firefox-gateway --restart unless-stopped \
  -p 6080:8080 \
  -e PUBLIC_IP="$PUBLIC_IP" \
  -e ADMIN_KEY="$ADMIN_KEY" \
  -v /usr/bin/docker:/usr/bin/docker:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v firefox_gateway_state:/data \
  firefox-gateway:local >/dev/null

sleep 5
curl -fsS http://127.0.0.1:6080/health
printf '\nGateway ready at http://%s:6080/\n' "$PUBLIC_IP"

read -r -p 'Cloudflare Tunnel configure karna hai? [y/N]: ' ENABLE_CF
if [[ ! "$ENABLE_CF" =~ ^[Yy]$ ]]; then
  echo "Cloudflare skipped. Setup complete."
  exit 0
fi

echo
 echo 'Cloudflare login command ab authorization URL dikhayega.'
echo 'URL ko apne browser mein open karke domain select/authorize karein.'
cloudflared tunnel login

read -r -p 'Apna Cloudflare root domain (example.com) dein: ' ROOT_DOMAIN
read -r -p 'Subdomain kya rakhna hai (example: firefox): ' SUBDOMAIN
ROOT_DOMAIN="${ROOT_DOMAIN#http://}"
ROOT_DOMAIN="${ROOT_DOMAIN#https://}"
ROOT_DOMAIN="${ROOT_DOMAIN%%/*}"
HOSTNAME="${SUBDOMAIN}.${ROOT_DOMAIN}"
TUNNEL_NAME="firefox-session"

if cloudflared tunnel list --name "$TUNNEL_NAME" 2>/dev/null | grep -q "$TUNNEL_NAME"; then
  TUNNEL_ID="$(cloudflared tunnel list --name "$TUNNEL_NAME" --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
else
  cloudflared tunnel create "$TUNNEL_NAME"
  TUNNEL_ID="$(cloudflared tunnel list --name "$TUNNEL_NAME" --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
fi

CRED_FILE="/root/.cloudflared/${TUNNEL_ID}.json"
CONFIG_FILE="/etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cat > "$CONFIG_FILE" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED_FILE}
ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:6080
  - service: http_status:404
EOF
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" || true
cloudflared service uninstall >/dev/null 2>&1 || true
cloudflared service install
systemctl enable --now cloudflared

printf '\nCloudflare URL ready: https://%s/\n' "$HOSTNAME"
printf 'Firefox login username: session ID\nFirefox login password: session password\n'
printf 'Admin API key: %s\n' "$ADMIN_KEY"
