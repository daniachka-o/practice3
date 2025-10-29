import os
import time
import uuid
import base64
import requests
from requests import Session
from typing import Any, Dict, Optional


class GigaChatClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        auth_url: Optional[str] = None,
        api_url: Optional[str] = None,
        models_url: Optional[str] = None,
        scope: str = "GIGACHAT_API_PERS",
        default_model: str = "GigaChat-2-Max",
        verify_ssl: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.client_id = client_id or os.environ.get("GIGACHAT_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("GIGACHAT_CLIENT_SECRET", "")
        self.auth_url = (
            auth_url
            or os.environ.get("GIGACHAT_AUTH_URL")
            or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        )
        self.api_url = (
            api_url
            or os.environ.get("GIGACHAT_URL")
            or "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        )
        self.models_url = (
            models_url
            or os.environ.get("GIGACHAT_MODELS_URL")
            or "https://gigachat.devices.sberbank.ru/api/v1/model"
        )
        self.scope = scope
        self.default_model = os.environ.get("GIGACHAT_MODEL", default_model)
        self.verify_ssl = verify_ssl
        self._timeout = timeout

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._session: Session = Session()

    def _is_token_valid(self) -> bool:
        return bool(self._access_token) and time.time() < self._expires_at - 30

    def _authorize(self) -> Dict[str, Any]:
        if not self.client_id or not self.client_secret or not self.auth_url:
            raise RuntimeError("GigaChat credentials/auth_url are not configured.")
        auth_key = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
        }
        data = {"scope": self.scope}
        resp = self._session.post(self.auth_url, headers=headers, data=data, verify=self.verify_ssl, timeout=self._timeout)
        if not resp.ok:
            raise RuntimeError(f"GigaChat auth failed: {resp.status_code} {resp.text}")
        body = resp.json()
        self._access_token = body.get("access_token")
        expires_in = body.get("expires_in")
        expires_at = body.get("expires_at")
        if isinstance(expires_in, (int, float)):
            self._expires_at = time.time() + float(expires_in) - 30
        elif isinstance(expires_at, (int, float)):
            self._expires_at = float(expires_at) - 30
        else:
            self._expires_at = time.time() + 60 * 60 * 24
        return body

    def get_access_token(self) -> str:
        if not self._is_token_valid():
            self._authorize()
        if not self._access_token:
            raise RuntimeError("GigaChat access token is not available after auth.")
        return self._access_token

    def send_chat(self, user_text: str, model: Optional[str] = None, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self.api_url:
            raise RuntimeError("GIGACHAT_URL is not configured.")
        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [],
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": user_text})

        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = self._session.post(self.api_url, headers=headers, json=payload, verify=self.verify_ssl, timeout=self._timeout)
        if resp.status_code == 401:
            # try refresh once
            self._authorize()
            token = self.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = self._session.post(self.api_url, headers=headers, json=payload, verify=self.verify_ssl, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def get_models(self) -> Dict[str, Any]:
        if not self.models_url:
            raise RuntimeError("GIGACHAT_MODELS_URL is not configured.")
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = self._session.get(self.models_url, headers=headers, verify=self.verify_ssl, timeout=self._timeout)
        if resp.status_code == 401:
            self._authorize()
            token = self.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = self._session.get(self.models_url, headers=headers, verify=self.verify_ssl, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def get_completion_text(response: Dict[str, Any], default: str = "") -> str:
        try:
            return response["choices"][0]["message"]["content"]
        except Exception:
            return default
