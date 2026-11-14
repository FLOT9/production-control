from uuid import uuid4

import httpx
from pydantic import SecretStr


class GigaChatClient:
    def __init__(self, auth_key: SecretStr, model: str, timeout_seconds: int) -> None:
        self.auth_key = auth_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Basic {self.auth_key.get_secret_value()}",
                    "RqUID": str(uuid4()),
                },
                data={"scope": "GIGACHAT_API_PERS"},
            )
            response.raise_for_status()
            return response.json()["access_token"]
