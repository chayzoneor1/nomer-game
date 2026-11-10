#!/usr/bin/env bash
# Продление сертификата (раз в ~2 месяца). Сервер сам подхватит новый файл в течение часа.
set -e
DOMAIN="${1:-nomergram-bot.duckdns.org}"
export DuckDNS_Token="${DUCKDNS_TOKEN:?export DUCKDNS_TOKEN=...}"
"$HOME/.acme.sh/acme.sh" --renew -d "$DOMAIN" --force --dnssleep 40
"$HOME/.acme.sh/acme.sh" --install-cert -d "$DOMAIN" --fullchain-file certs/fullchain.pem --key-file certs/privkey.pem
