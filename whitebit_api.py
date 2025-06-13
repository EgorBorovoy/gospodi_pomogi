import hmac
import hashlib
import json
import time
from typing import Dict, Any
import httpx

class WhiteBitAPI:
    """Класс для работы с API биржи WhiteBit"""
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Инициализация API клиента
        :param api_key: API ключ от WhiteBit
        :param api_secret: API секрет от WhiteBit
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://whitebit.com"
        
    def _generate_signature(self, endpoint: str, data: Dict[str, Any]) -> str:
        """Генерация подписи для приватных запросов"""
        data["request"] = endpoint
        data["nonce"] = str(int(time.time() * 1000))
        
        encoded_data = json.dumps(data).encode('utf-8')
        signature = hmac.new(self.api_secret.encode('utf-8'),
                           encoded_data,
                           hashlib.sha512).hexdigest()
        return signature
        
    async def get_balance(self) -> Dict[str, Any]:
        """Получение баланса аккаунта"""
        endpoint = "/api/v4/trade-account/balance"
        data = {}
        
        signature = self._generate_signature(endpoint, data)
        
        headers = {
            "Content-Type": "application/json",
            "X-TXC-APIKEY": self.api_key,
            "X-TXC-PAYLOAD": json.dumps(data),
            "X-TXC-SIGNATURE": signature
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Ошибка получения баланса: {response.text}") 