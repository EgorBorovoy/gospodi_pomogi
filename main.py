from fastapi import FastAPI, Request, HTTPException
import httpx
import json
from datetime import datetime
from typing import Dict, Any, Optional
import os
from dotenv import load_dotenv
import logging
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Настройки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")  # Опциональный секрет для безопасности

# Проверяем, что настройки есть
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

# Создаём приложение
app = FastAPI(title="Trading Webhook to Telegram")

# Клиент для HTTP запросов
client = httpx.AsyncClient(timeout=30.0)


async def send_telegram_message(text: str, disable_notification: bool = False):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": disable_notification
    }
    
    try:
        response = await client.post(url, json=payload)
        result = response.json()
        if not result.get("ok"):
            logger.error(f"Telegram API error: {result}")
        return result
    except Exception as e:
        logger.error(f"Error sending to Telegram: {e}")
        return None


@app.on_event("startup")
async def startup_event():
    """При запуске отправляем уведомление в Telegram"""
    message = "🚀 <b>Webhook сервис запущен!</b>\n\n"
    message += f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    message += "✅ Готов принимать вебхуки"
    await send_telegram_message(message)


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
    """Универсальный эндпоинт для любых вебхуков"""
    try:
        # Проверка секрета (если настроен)
        if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid secret")
        
        # Получаем тело запроса
        body = await request.json()
        
        # Логируем
        logger.info(f"Received webhook: {json.dumps(body)[:200]}...")
        
        # Формируем красивое сообщение
        message = f"🔔 <b>Новый вебхук!</b>\n\n"
        message += f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        message += f"📊 Данные:\n<pre>{json.dumps(body, indent=2, ensure_ascii=False)[:3000]}</pre>"
        
        # Отправляем в Telegram
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