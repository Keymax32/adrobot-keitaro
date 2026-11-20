from pathlib import Path
from typing import Literal

import pycountry
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, PositiveInt, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import tracker
from .db import Stream, engine
from .editor import edit, merge, remote_offers

app = FastAPI(title="Adrobot")
static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(static / "index.html")


class CampaignInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    country: str
    domain_id: PositiveInt
    group_id: PositiveInt
    traffic_source_id: PositiveInt
    offer_id: PositiveInt

    @field_validator("country")
    @classmethod
    def valid_country(cls, v):
        code = v.strip().upper()
        if pycountry.countries.get(alpha_2=code) is None:
            raise ValueError("Нужен двухбуквенный ISO-код страны.")
        return code

    @field_validator("name")
    @classmethod
    def valid_name(cls, v):
        if not v.strip():
            raise ValueError("Введите название.")
        return v.strip()


class Change(BaseModel):
    version: PositiveInt
    action: Literal["add", "remove", "restore", "pin", "cancel", "push"]
    offer_id: PositiveInt | None = None


def db():
    with Session(engine) as session:
        yield session


def choices(resource, **params):
    items = tracker.request("GET", resource, params=params)
    return [dict(id=int(x["id"]), name=x.get("name") or x.get("domain") or str(x["id"]))
            for x in items if x.get("state") != "deleted"]


@app.get("/api/settings")
def settings():
    return dict(domains=choices("domains"), groups=choices("groups", type="campaigns"),
                sources=choices("traffic_sources"))


@app.get("/api/offers")
def offers(q: str = ""):
    needle = q.strip().casefold()
    rows = choices("offers")
    return sorted((x for x in rows if needle in str(x["id"]) or needle in x["name"].casefold()),
                  key=lambda x: str(x["id"]) != needle)[:50]


@app.post("/api/campaigns", status_code=201)
def create(data: CampaignInput):
    return tracker.create_campaign(data)


def streams_for(session, cid):
    return session.scalars(select(Stream).where(Stream.campaign_id == cid)
                           .order_by(Stream.position, Stream.id)).all()


def view(row):
    return dict(id=row.id, name=row.name, editable=row.editable, version=row.version,
                dirty=row.draft != row.published, offers=row.draft)


@app.get("/api/campaigns/{cid}/streams")
def local(cid: PositiveInt, session: Session = Depends(db)):
    return [view(row) for row in streams_for(session, cid)]


@app.post("/api/campaigns/{cid}/fetch")
def fetch(cid: PositiveInt, session: Session = Depends(db)):
    session.execute(text("BEGIN IMMEDIATE"))
    old = {row.id: row for row in streams_for(session, cid)}
    if any(r.draft != r.published for r in old.values()):
        raise HTTPException(409, "Опубликуйте или отмените черновики перед загрузкой.")
    streams = tracker.request("GET", f"campaigns/{cid}/streams")
    names = {x["id"]: x["name"] for x in choices("offers")}
    for flow in streams:
        sid = int(flow["id"])
        row = old.pop(sid, None)
        if row is None:
            row = Stream(id=sid, campaign_id=cid, version=0, published=[])
            session.add(row)
        row.version += 1
        row.name = flow["name"]
        row.position = flow["position"]
        row.editable = flow["schema"] == "landings"
        row.published = merge(row.published, flow.get("offers") or [], names)
        row.draft = row.published
    for row in old.values():
        session.delete(row)
    session.commit()
    return [view(row) for row in streams_for(session, cid)]


def signature(offers):
    return sorted((int(o["offer_id"]), int(o["share"]), o.get("state", "active")) for o in offers)


@app.post("/api/streams/{sid}")
def change(sid: PositiveInt, data: Change, session: Session = Depends(db)):
    session.execute(text("BEGIN IMMEDIATE"))
    row = session.get(Stream, sid)
    if row is None:
        raise HTTPException(404, "Сначала загрузите потоки.")
    if row.version != data.version:
        raise HTTPException(409, "Поток изменился. Откройте кампанию ещё раз.")
    if data.action == "cancel":
        row.draft = row.published
    elif not row.editable:
        raise HTTPException(409, "В этом потоке нет ротации офферов.")
    elif data.action == "push":
        if row.draft != row.published:
            remote = tracker.request("GET", f"streams/{sid}")
            current = signature(remote.get("offers") or [])
            desired = remote_offers(row.draft)
            if remote["schema"] != "landings" or int(remote["campaign_id"]) != row.campaign_id:
                raise HTTPException(409, "Тип или кампания потока изменились в Keitaro.")
            if current != signature(desired):
                if current != signature(remote_offers(row.published)):
                    raise HTTPException(409, "Офферы изменены в Keitaro. Отмените черновик и загрузите потоки.")
                updated = tracker.request("PUT", f"streams/{sid}", json={"offers": desired})
                if signature(updated.get("offers") or []) != signature(desired):
                    raise HTTPException(502, "Keitaro вернул другие доли. Проверьте поток.")
            row.published = row.draft
    else:
        if data.offer_id is None:
            raise HTTPException(422, "Нужен ID оффера.")
        name = None
        if data.action == "add":
            name = tracker.request("GET", f"offers/{data.offer_id}")["name"]
        row.draft = edit(row.draft, data.offer_id, data.action, name)
    row.version += 1
    session.commit()
    return view(row)

