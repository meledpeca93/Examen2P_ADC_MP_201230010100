import requests
from django.conf import settings


class APIError(Exception):
    pass


def api_request(method, path, payload=None):
    url = f"{settings.API_BASE_URL.rstrip('/')}{path}"

    try:
        response = requests.request(method, url, json=payload, timeout=5)
    except requests.RequestException as exc:
        raise APIError("No se pudo conectar con la API.") from exc

    if response.status_code == 204:
        return None

    try:
        data = response.json()
    except ValueError as exc:
        raise APIError(
            f"La API devolvió una respuesta no válida (HTTP {response.status_code})."
        ) from exc

    if not response.ok:
        message = data.get("error") if isinstance(data, dict) else None
        raise APIError(message or f"La API respondió HTTP {response.status_code}.")

    return data