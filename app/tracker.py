import os
from uuid import uuid4
import httpx
from fastapi import HTTPException


def request(method, path, **kwargs):
    key = os.getenv("KEITARO_API_KEY")
    url = os.getenv("KEITARO_URL", "").rstrip("/")
    if not key or not url.startswith("https://"):
        raise HTTPException(503, "Укажите KEITARO_URL (HTTPS) и KEITARO_API_KEY в .env.")
    try:
        res = httpx.request(method, f"{url}/admin_api/v1/{path}", headers={"Api-Key": key},
                            timeout=20, **kwargs)
        res.raise_for_status()
        return res.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Keitaro: {method} /{path} — HTTP {exc.response.status_code}") from exc
    except (ValueError, httpx.RequestError) as exc:
        raise HTTPException(502, f"Не получен ответ Keitaro на {method} /{path}.") from exc


def create_campaign(data):
    prefix = os.getenv("CAMPAIGN_PREFIX", "test_kappes_")
    name = data.name if data.name.startswith(prefix) else prefix + data.name
    request("GET", f"offers/{data.offer_id}")
    campaign = request("POST", "campaigns", json=dict(
        name=name, type="position", state="disabled", alias=uuid4().hex[:16],
        domain_id=data.domain_id, group_id=data.group_id, traffic_source_id=data.traffic_source_id))
    cid = campaign["id"]
    base = dict(campaign_id=cid, state="active", collect_clicks=True)
    try:
        request("POST", "streams", json=dict(base, name=f"{data.country} → Google",
                type="regular", position=1, schema="redirect", action_type="http",
                action_payload="https://www.google.com/",
                filters=[dict(name="country", mode="accept", payload=[data.country])]))
        request("POST", "streams", json=dict(base, name="Офферы", type="default", position=2,
                schema="landings", action_type="http",
                offers=[dict(offer_id=data.offer_id, share=100, state="active")]))
        request("PUT", f"campaigns/{cid}", json={"state": "active"})
    except HTTPException as exc:
        raise HTTPException(502, f"Кампания #{cid} создана. Проверьте потоки и статус перед повтором. {exc.detail}") from exc
    return dict(id=cid, name=name)

