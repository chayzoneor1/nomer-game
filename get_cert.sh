#!/usr/bin/env bash
# Бесплатный HTTPS-сертификат Let's Encrypt для домена DuckDNS (без открытия порта 80).
# Запуск в консоли хостинга:
#   export DUCKDNS_TOKEN=твой_токен_с_duckdns.org
#   bash get_cert.sh nomergram-bot.duckdns.org твоя@почта.ru
set -e
DOMAIN="${1:-nomergram-bot.duckdns.org}"
MAIL="${2:-admin@example.com}"
[ -n "$DUCKDNS_TOKEN" ] || { echo "Сначала: export DUCKDNS_TOKEN=токен_с_duckdns.org"; exit 1; }
export DuckDNS_Token="$DUCKDNS_TOKEN"
[ -d "$HOME/.acme.sh" ] || curl -s https://get.acme.sh | sh -s email="$MAIL"
"$HOME/.acme.sh/acme.sh" --set-default-ca --server letsencrypt
"$HOME/.acme.sh/acme.sh" --issue --dns dns_duckdns -d "$DOMAIN" --dnssleep 40 || true
mkdir -p certs
"$HOME/.acme.sh/acme.sh" --install-cert -d "$DOMAIN" --fullchain-file certs/fullchain.pem --key-file certs/privkey.pem
echo "Готово: certs/fullchain.pem и certs/privkey.pem. Перезапусти сервер (кнопка «Рестарт»)."
