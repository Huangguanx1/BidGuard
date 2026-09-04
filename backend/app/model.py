import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .config import Settings


class ModelError(Exception):
    pass


def check_model(settings: Settings) -> str:
    if not settings.model_base_url or not settings.model_api_key or not settings.model_name:
        raise ModelError("模型配置不完整，请检查 .env")

    request = Request(
        f"{settings.model_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": settings.model_name,
                "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                "temperature": 0,
                "max_tokens": 8,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.model_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        proxy_handler = ProxyHandler({}) if settings.model_bypass_proxy else ProxyHandler()
        with build_opener(proxy_handler).open(
            request, timeout=settings.model_timeout_seconds
        ) as response:
            payload = json.load(response)
        return str(payload["choices"][0]["message"]["content"]).strip()
    except HTTPError as exc:
        raise ModelError(f"模型接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise ModelError("无法连接模型接口") from exc
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ModelError("模型接口返回格式不兼容") from exc
