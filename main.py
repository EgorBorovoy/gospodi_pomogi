from fastapi import FastAPI, Request, HTTPException
import httpx
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
from dotenv import load_dotenv
import logging
from pydantic import BaseModel
from whitebit_api import WhiteBitAPI

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Настройки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WHITEBIT_API_KEY = os.getenv("WHITEBIT_API_KEY")
WHITEBIT_API_SECRET = os.getenv("WHITEBIT_API_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # URL вашего сервера, например https://your-app.up.railway.app/webhook

# Проверяем, что настройки есть
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WHITEBIT_API_KEY, WHITEBIT_API_SECRET, WEBHOOK_URL]):
    logger.error("Missing required environment variables")

# Создаём приложение
app = FastAPI(title="Trading Webhook to Telegram")

# Клиент для HTTP запросов
client = httpx.AsyncClient(timeout=30.0)

# Создаём WhiteBit API клиент
whitebit = WhiteBitAPI(WHITEBIT_API_KEY, WHITEBIT_API_SECRET)

# Список доступных команд
COMMANDS = {
    "/start": "📋 Показать список команд",
    "/balance": "💰 Показать баланс на бирже",
    "/help": "❓ Показать справку по командам"
}

async def setup_telegram_webhook():
    """Настройка вебхука для Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    webhook_url = f"{WEBHOOK_URL}/webhook"
    
    try:
        # Сначала удалим текущий вебхук
        await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        
        # Установим новый вебхук
        response = await client.post(url, json={
            "url": webhook_url,
            "allowed_updates": ["message"]
        })
        result = response.json()
        logger.info(f"Webhook setup result: {result}")
        return result.get("ok", False)
    except Exception as e:
        logger.error(f"Error setting up webhook: {e}")
        return False

def create_keyboard_markup() -> Dict:
    """Создание клавиатуры с командами"""
    keyboard = []
    row = []
    for i, (cmd, desc) in enumerate(COMMANDS.items()):
        # Создаем кнопку с командой
        button = {"text": desc.split(' ', 1)[1]}  # Берем описание без эмодзи
        row.append(button)
        
        # Формируем ряды по 2 кнопки
        if len(row) == 2 or i == len(COMMANDS) - 1:
            keyboard.append(row)
            row = []
    
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

async def send_telegram_message(text: str, disable_notification: bool = False):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": disable_notification,
        "reply_markup": create_keyboard_markup()
    }
    
    try:
        logger.info(f"Sending message to Telegram: {text[:100]}...")
        response = await client.post(url, json=payload)
        result = response.json()
        logger.info(f"Telegram API response: {result}")
        
        if not result.get("ok"):
            logger.error(f"Telegram API error: {result}")
        return result
    except Exception as e:
        logger.error(f"Error sending to Telegram: {e}")
        return None

def get_commands_list() -> str:
    """Формирование списка команд"""
    message = "🤖 <b>Доступные команды:</b>\n\n"
    for cmd, desc in COMMANDS.items():
        message += f"{cmd} - {desc}\n"
    return message

async def process_telegram_command(text: str, chat_id: str) -> str:
    """Обработка команд от пользователя из Telegram"""
    try:
        # DEBUG: Логируем входящую команду и chat_id
        logger.info(f"Processing command: {text} from chat_id: {chat_id}")
        
        # Проверяем, что команда пришла от разрешенного чата
        if chat_id != TELEGRAM_CHAT_ID:
            logger.warning(f"Unauthorized chat_id: {chat_id}")
            return "⛔️ Доступ запрещен"
        
        if text.startswith('/start') or text.startswith('/help'):
            return get_commands_list()
            
        elif text.startswith('/balance'):
            # DEBUG: Логируем запрос баланса
            logger.info("Requesting balance from WhiteBit API...")
            
            # Получаем баланс
            balance = await whitebit.get_balance()
            
            # DEBUG: Логируем полученный баланс
            logger.info(f"Received balance: {balance}")
            
            # Форматируем ответ
            message = "💰 <b>Баланс на WhiteBit:</b>\n\n"
            for currency, data in balance.items():
                if float(data.get('available', 0)) > 0:
                    message += f"• {currency}: {data['available']} (в ордерах: {data.get('freeze', 0)})\n"
            return message
            
        else:
            return "❌ Неизвестная команда. Отправьте /help для списка команд."
            
    except Exception as e:
        logger.error(f"Error processing command: {e}")
        return f"❌ Ошибка: {str(e)}"

@app.on_event("startup")
async def startup_event():
    """При запуске отправляем уведомление в Telegram"""
    try:
        # Настраиваем вебхук
        webhook_setup = await setup_telegram_webhook()
        logger.info(f"Telegram webhook setup: {'success' if webhook_setup else 'failed'}")
        
        # Проверяем подключение к WhiteBit API
        api_status = await whitebit.test_connection()
        logger.info(f"WhiteBit API connection test: {'success' if api_status else 'failed'}")
        
        message = "🚀 <b>Бот запущен!</b>\n\n"
        if api_status:
            message += "✅ Подключение к WhiteBit API успешно\n\n"
        else:
            message += "❌ Ошибка подключения к WhiteBit API\n\n"
            
        message += get_commands_list()
        await send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
        await send_telegram_message(f"❌ Ошибка при запуске бота: {str(e)}")

@app.get("/")
async def root():
    """Проверка что сервис работает"""
    return {
        "status": "ok",
        "service": "Trading Webhook to Telegram",
        "version": "1.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/webhook")
async def receive_webhook(request: Request, secret: Optional[str] = None):
    """Универсальный эндпоинт для вебхуков"""
    try:
        # Проверка секрета (если настроен)
        if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid secret")
        
        # Получаем тело запроса
        body = await request.json()
        logger.info(f"Received webhook body: {json.dumps(body)}")  # DEBUG: Полное логирование
        
        # Проверяем, не команда ли это из Telegram
        if "message" in body and "text" in body["message"]:
            command_text = body["message"]["text"]
            chat_id = str(body["message"]["chat"]["id"])
            
            # DEBUG: Логируем детали сообщения
            logger.info(f"Received Telegram message: text='{command_text}', chat_id={chat_id}")
            
            command_response = await process_telegram_command(command_text, chat_id)
            await send_telegram_message(command_response)
            return {"status": "success", "message": "Command processed"}
        
        # Если не команда, обрабатываем как обычный вебхук
        message = f"🔔 <b>Новый вебхук!</b>\n\n"
        message += f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        message += f"📊 Данные:\n<pre>{json.dumps(body, indent=2, ensure_ascii=False)[:3000]}</pre>"
        
        await send_telegram_message(message)
        
        return {"status": "success", "message": "Sent to Telegram"}
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        error_msg = f"❌ Ошибка обработки вебхука: {str(e)}"
        await send_telegram_message(error_msg)
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel

# Модель для торгового сигнала
class TradingSignalRequest(BaseModel):
    symbol: str
    side: str
    amount: float
    price: Optional[float] = None
    secret: Optional[str] = None

@app.post("/trading-signal")
async def trading_signal(request: TradingSignalRequest):
    """Специальный эндпоинт для торговых сигналов"""
    # Проверка секрета
    if WEBHOOK_SECRET and request.secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")
    
    # Валидация
    if request.side not in ["buy", "sell"]:
        raise HTTPException(status_code=400, detail="Side must be 'buy' or 'sell'")
    
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    # Формируем красивое сообщение
    message = f"📈 <b>Торговый сигнал</b>\n\n"
    message += f"• Пара: <code>{request.symbol}</code>\n"
    message += f"• Действие: <b>{'🟢 ПОКУПКА' if request.side == 'buy' else '🔴 ПРОДАЖА'}</b>\n"
    message += f"• Количество: <code>{request.amount}</code>\n"
    
    if request.price:
        message += f"• Цена: <code>{request.price}</code>\n"
        message += f"• Тип: Лимитный ордер\n"
    else:
        message += f"• Тип: Рыночный ордер\n"
    
    message += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    
    # Отправляем в Telegram
    await send_telegram_message(message)
    
    logger.info(f"Trading signal processed: {request.symbol} {request.side} {request.amount} @ {request.price}")
    
    return {
        "status": "success",
        "signal": {
            "symbol": request.symbol,
            "side": request.side,
            "amount": request.amount,
            "price": request.price,
            "timestamp": datetime.now().isoformat()
        }
    }


@app.post("/tradingview")
async def tradingview_webhook(request: Request):
    """Специальный эндпоинт для TradingView"""
    try:
        # TradingView может отправлять как JSON, так и текст
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            data = await request.json()
            message_text = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            # Текстовый формат
            body = await request.body()
            message_text = body.decode('utf-8')
        
        # Формируем сообщение
        message = f"📊 <b>TradingView Alert</b>\n\n"
        message += f"<pre>{message_text[:1000]}</pre>\n"
        message += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        await send_telegram_message(message)
        
        return {"status": "success", "source": "tradingview"}
        
    except Exception as e:
        logger.error(f"TradingView webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Для Railway важно слушать на правильном порту
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)