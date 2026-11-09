# -*- coding: utf-8 -*-
"""Единая точка запуска для хостинга: кнопка «Старт» в панели запускает сервер игры и бота в одном процессе."""
import asyncio, threading

import server

srv = server.make_server()
threading.Thread(target=srv.serve_forever, daemon=True).start()
print(f"Крути Номер: {'https' if srv.tls else 'http'}://{server.HOST}:{server.PORT} · игра: {server.GAME_DIR} · эпоха данных: {server.DATA_EPOCH}")
if not srv.tls and server.PORT == 443:
    print("ВНИМАНИЕ: порт 443 без SSL_CERT/SSL_KEY — это обычный HTTP. Telegram откроет игру только по HTTPS (см. README, раздел «HTTPS»).")
try:
    import bot
    asyncio.run(bot.main())
except SystemExit as e:
    print(e)
    threading.Event().wait()          # сервер продолжает работать и без бота
except KeyboardInterrupt:
    pass
