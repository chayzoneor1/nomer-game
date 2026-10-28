1) pip install -r requirements.txt
2) Скопируй .env.example в .env, впиши НОВЫЙ токен и GAME_URL (публичный https-адрес сервера).
3) Сервер (игра + API + карточки): uvicorn server:app --host 0.0.0.0 --port 8000
   Нужен https-домен (nginx/Caddy/Cloudflare Tunnel) — Telegram Mini App работает только по https.
4) Бот: python NomerGame_FULL_Project/bot.py
5) В BotFather: /setmenubutton или Mini App → тот же GAME_URL.
