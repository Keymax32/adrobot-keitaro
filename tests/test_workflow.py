from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import main
from app.db import Base


@pytest.fixture
def site(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "state.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    flow = dict(id=8, campaign_id=7, position=2, name="Offers", schema="landings",
                offers=[dict(offer_id=1, state="active", share=100)])
    redirect = dict(id=9, campaign_id=7, position=1, name="Google", schema="redirect", offers=[])

    def upstream(method, path, **kwargs):
        if path == "offers":
            return [dict(id=i, name=f"Offer {i}") for i in [1, 2, 3]]
        if path == "offers/2":
            return dict(id=2, name="Offer 2")
        if path == "campaigns/7/streams":
            return deepcopy([redirect, flow])
        assert path == "streams/8"
        if method == "PUT":
            assert set(kwargs["json"]) == {"offers"}
            flow.update(kwargs["json"])
        return deepcopy(flow)

    monkeypatch.setattr(main.tracker, "request", upstream)
    yield TestClient(main.app), flow
    engine.dispose()


def test_edit_publish_fetch_and_cancel(site):
    client, flow = site
    redirect, row = client.post("/api/campaigns/7/fetch").json()
    assert not redirect["editable"]

    def change(action, oid=None):
        nonlocal row
        res = client.post("/api/streams/8", json=dict(version=row["version"], action=action, offer_id=oid))
        assert res.status_code == 200, res.text
        row = res.json()

    change("add", 2)
    assert len(flow["offers"]) == 1 and row["dirty"]
    assert client.post("/api/campaigns/7/fetch").status_code == 409
    assert client.get("/api/campaigns/7/streams").json()[1] == row
    change("cancel")
    assert len(row["offers"]) == 1
    change("add", 2)
    change("push")
    assert [o["share"] for o in flow["offers"]] == [50, 50]
    change("remove", 2)
    change("push")
    assert row["offers"][1]["removed"] and len(flow["offers"]) == 1
    change("restore", 2)
    change("push")
    flow["offers"] = [dict(offer_id=2, share=100, state="active")]
    row = client.post("/api/campaigns/7/fetch").json()[1]
    assert row["offers"][1]["removed"]
    change("restore", 1)
    flow["offers"].append(dict(offer_id=3, share=0, state="active"))
    assert client.post("/api/streams/8", json=dict(version=row["version"], action="push")).status_code == 409
    assert client.post("/api/streams/8", json=dict(version=1, action="cancel")).status_code == 409

