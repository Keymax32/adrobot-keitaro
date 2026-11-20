from copy import deepcopy
from fastapi import HTTPException


def remote_offers(rows):
    return [dict(offer_id=r["id"], share=r["share"], state=r["state"])
            for r in rows if not r["removed"]]


def merge(previous, offers, names):
    old = {r["id"]: r for r in previous}
    result = []
    for offer in offers:
        oid = int(offer["offer_id"])
        prior = old.pop(oid, {})
        result.append(dict(id=oid, name=names.get(oid) or prior.get("name") or f"#{oid}",
                           state=offer.get("state", "active"), share=int(offer["share"]),
                           pinned=bool(prior.get("pinned")), removed=False))
    return result + [dict(r, removed=True, share=0, pinned=False) for r in old.values()]


def redistribute(rows):
    active = [r for r in rows if not r["removed"] and r["state"] == "active"]
    if not active:
        return
    free = [r for r in active if not r["pinned"]]
    remaining = 100 - sum(r["share"] for r in active if r["pinned"])
    if remaining < 0 or (not free and remaining != 0):
        raise HTTPException(409, "Невозможно распределить 100%. Снимите закрепление доли.")
    if free:
        share, extra = divmod(remaining, len(free))
        for i, row in enumerate(free):
            row["share"] = share + int(i < extra)


def edit(rows, oid, action, name=None):
    result = deepcopy(rows)
    row = next((r for r in result if r["id"] == oid), None)
    if action == "add":
        if row:
            raise HTTPException(409, "Оффер уже есть в списке.")
        result.append(dict(id=oid, name=name, removed=False, pinned=False, share=0, state="active"))
    elif row is None:
        raise HTTPException(404, "Привязка не найдена.")
    elif action == "restore" and row["removed"]:
        row.update(removed=False, state="active")
    elif action == "remove" and not row["removed"]:
        row.update(removed=True, pinned=False, share=0)
    elif action == "pin" and not row["removed"] and row["state"] == "active":
        row["pinned"] = not row["pinned"]
        return result
    else:
        raise HTTPException(409, "Действие недоступно для этой привязки.")
    redistribute(result)
    return result

