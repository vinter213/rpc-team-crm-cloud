RPC CRM TELEGRAM PHONE NOTIFICATIONS
====================================

Это обновление добавляет уведомления на телефон через Telegram.

Как работает:
Клиент оставляет заказ на сайте -> сервер CRM создаёт заказ -> тебе в Telegram приходит сообщение:
- номер заявки
- клиент
- контакт
- услуга
- бюджет
- дедлайн
- описание

Настройка Telegram:

1. Открой Telegram и найди @BotFather.
2. Напиши /newbot.
3. Создай бота и скопируй токен.
4. Напиши своему новому боту любое сообщение: Привет.
5. Узнай свой chat_id через @userinfobot или @RawDataBot.
6. Открой Render -> твой сервис rpc-team-crm -> Environment.
7. Добавь переменные:
   TELEGRAM_BOT_TOKEN = токен от BotFather
   TELEGRAM_CHAT_ID = твой chat_id
8. Нажми Save Changes и сделай deploy.
9. Проверь /docs, там должен появиться:
   POST /admin/telegram/test

После этого новые заявки с сайта будут приходить на телефон в Telegram.

Важно:
Telegram-уведомления бесплатные.
SMS на номер телефона обычно платные, через Twilio/SMS.ru/etc.
