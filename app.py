from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any
import uuid

app = FastAPI(title="Demo3 HealthPlan API (Python Version)")

# ===============================
# 1. Security - very simple token
# ===============================

FAKE_TOKEN = "demo-token"


def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Very simple Bearer token check:
    Authorization: Bearer demo-token
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    if token != FAKE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"user": "demo-user"}


@app.get("/token")
def get_token():
    """
    For demo: just return a fixed token.
    In real life you would use JWT etc.
    """
    return {"token": FAKE_TOKEN}


# ===============================
# 2. Pydantic models == JSON Schema
# ===============================

class PlanCostShares(BaseModel):
    deductible: float
    copay: float
    _org: Optional[str] = None
    objectId: str
    objectType: str


class LinkedService(BaseModel):
    name: str
    _org: Optional[str] = None
    objectId: str
    objectType: str


class PlanServiceCostShares(BaseModel):
    deductible: float
    copay: float
    _org: Optional[str] = None
    objectId: str
    objectType: str


class LinkedPlanService(BaseModel):
    linkedService: LinkedService
    planserviceCostShares: PlanServiceCostShares
    _org: Optional[str] = None
    objectId: str
    objectType: str


class HealthPlan(BaseModel):
    planCostShares: PlanCostShares
    linkedPlanServices: List[LinkedPlanService]
    _org: Optional[str] = None
    objectId: str
    objectType: str
    planType: str
    creationDate: str

    # Optional: version for "update if not changed"
    version: int = Field(default=1)


# ===============================
# 3. In-memory KV store + "index"
# ===============================

# KV store: objectId -> HealthPlan dict
kv_store: Dict[str, Dict[str, Any]] = {}

# "Index": simulate Elasticsearch parent-child index.
# For simplicity: we just keep a copy of the same data,
# plus a child index on linked service name.
index_store: Dict[str, Dict[str, Any]] = {}
child_index_by_service_name: Dict[str, List[str]] = {}  # serviceName -> list of planIds


def build_index_for_plan(plan: Dict[str, Any]):
    """
    Simulate ES parent-child index:
    - Parent: healthplan
    - Child: each linkedPlanService
    """
    plan_id = plan["objectId"]
    index_store[plan_id] = plan

    # clear old entries for this plan
    for name, plan_ids in list(child_index_by_service_name.items()):
        child_index_by_service_name[name] = [pid for pid in plan_ids if pid != plan_id]
        if not child_index_by_service_name[name]:
            del child_index_by_service_name[name]

    # add new children
    for lps in plan.get("linkedPlanServices", []):
        service_name = lps["linkedService"]["name"]
        child_index_by_service_name.setdefault(service_name.lower(), []).append(plan_id)


def delete_from_index(plan_id: str):
    index_store.pop(plan_id, None)
    # remove from child index
    for name, plan_ids in list(child_index_by_service_name.items()):
        child_index_by_service_name[name] = [pid for pid in plan_ids if pid != plan_id]
        if not child_index_by_service_name[name]:
            del child_index_by_service_name[name]


# ===============================
# 4. Deep merge for PATCH
# ===============================

def deep_merge(original: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge dictionaries: patch values override original.
    """
    for key, value in patch.items():
        if (
            key in original
            and isinstance(original[key], dict)
            and isinstance(value, dict)
        ):
            deep_merge(original[key], value)
        else:
            original[key] = value
    return original


# ===============================
# 5. REST API
# ===============================

@app.post("/healthplan", dependencies=[Depends(get_current_user)])
def create_healthplan(plan: HealthPlan):
    """
    Create healthplan:
    - validates JSON via Pydantic
    - stores in KV store
    - builds index (simulating ES parent-child)
    """
    plan_id = plan.objectId
    if plan_id in kv_store:
        raise HTTPException(status_code=409, detail="objectId already exists")

    plan_dict = plan.dict()
    kv_store[plan_id] = plan_dict
    build_index_for_plan(plan_dict)

    return {"status": "created", "doc": plan_dict}


@app.get("/healthplan/{plan_id}", dependencies=[Depends(get_current_user)])
def get_healthplan(plan_id: str):
    plan = kv_store.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Not found")
    return plan


@app.patch("/healthplan/{plan_id}", dependencies=[Depends(get_current_user)])
def patch_healthplan(
    plan_id: str,
    patch_body: Dict[str, Any],
    background_tasks: BackgroundTasks,
    if_match: Optional[int] = Header(None, alias="If-Match")
):
    """
    PATCH:
    - Deep merge
    - update version if If-Match matches
    - simulate queue: background task updates index
    """
    existing = kv_store.get(plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")

    # Optional: advanced semantics "update if not changed"
    if if_match is not None:
        current_version = existing.get("version", 1)
        if current_version != if_match:
            raise HTTPException(status_code=409, detail="Version conflict (update if not changed failed)")

    # Deep merge
    updated = deep_merge(existing.copy(), patch_body)

    # bump version
    updated["version"] = updated.get("version", 1) + 1

    # write back to KV
    kv_store[plan_id] = updated

    # simulate queue: background task "updates ES index"
    background_tasks.add_task(build_index_for_plan, updated)

    return {"status": "patched", "updated": updated}


@app.delete("/healthplan/{plan_id}", dependencies=[Depends(get_current_user)])
def delete_healthplan(plan_id: str):
    """
    Delete:
    - remove from KV store
    - remove from index (simulate cascaded delete)
    """
    existing = kv_store.pop(plan_id, None)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")

    delete_from_index(plan_id)

    return {"status": "deleted", "id": plan_id}


# ===============================
# 6. "Search with Parent-Child"
# ===============================

@app.get("/search/by-service", dependencies=[Depends(get_current_user)])
def search_by_service(service_name: str):
    """
    Search plans whose child service name matches (case-insensitive).
    This simulates an Elastic parent-child search:
    - child: linkedPlanService.linkedService.name
    - parent: healthplan
    """
    plan_ids = child_index_by_service_name.get(service_name.lower(), [])
    results = [index_store[pid] for pid in plan_ids if pid in index_store]
    return {"service_name": service_name, "hits": results}


# ===============================
# Root endpoint
# ===============================

@app.get("/")
def root():
    return {"message": "Demo3 HealthPlan API (Python FastAPI version) is running"}
