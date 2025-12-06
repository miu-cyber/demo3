
---

#  **README.md — Demo 3 HealthPlan REST API *````
# Demo 3 — HealthPlan REST API   
**Implementation: FastAPI + Pydantic + In-Memory KV Store + Simulated Elasticsearch Index**

This project fully implements the Demo 3 specifications, including structured
JSON validation, complete CRUD support, deep merge for PATCH, cascaded delete,
security, queueing, and parent-child search/indexing.  
All behavior aligns exactly with the assignment requirements.

---

##  1. Structured JSON Support (JSON Schema + Validation)
The API accepts complex hierarchical JSON defined by the instructor-provided
**HealthPlan JSON Schema**.  
Validation is performed automatically using **Pydantic**, enforcing:

- Required fields  
- Correct types  
- Nested object validation  
- Array item validation  

Invalid payloads return standard `422 Unprocessable Entity`.

---

## 2. CRUD Operations (Create, Read, Update, Delete)

### ✔ `POST /healthplan`
- Creates a new HealthPlan document  
- Validates JSON against the schema  
- Stores document in an in-memory key/value store  
- Returns `409 Conflict` if `objectId` already exists  

### ✔ `GET /healthplan/{id}`
- Retrieves document from key/value store  

### ✔ `PATCH /healthplan/{id}`
Implemented according to assignment requirements:

- **Deep merge** of nested fields  
- Updates only specified sub-objects  
- Non-specified fields preserved  
- Version bump after successful update  
- Background update of index (queue simulation)

### ✔ `DELETE /healthplan/{id}`
- Removes document from KV store  
- Removes parent entry from index  
- Removes all corresponding child entries  
- Repeated delete returns `404 Not Found`  
- Fully implements **cascaded delete** requirement

---

##  3. Deep Merge Support for PATCH (Assignment Requirement)
PATCH supports:

- Partial updates  
- Hierarchical field merge  
- Merge down to `linkedPlanServices` child level  

Example:

```json
{
  "planCostShares": { "copay": 25 },
  "planType": "HMO"
}
````

Only updates `copay` and `planType`, preserving all other fields.

---

##  4. Advanced Semantics: Update-If-Not-Changed (Version Control)

PATCH takes an `If-Match` header:

```
If-Match: <version_number>
```

* Update allowed only if version matches
* Otherwise server returns `409 Conflict`
* Demonstrates optimistic concurrency control

This fulfills the **“update-if-not-changed”** requirement.

---

##  5. Key/Value Storage Layer

All HealthPlan data is stored in an in-memory:

```
{ objectId → HealthPlan document }
```

KV storage is used by GET, PATCH, DELETE, and search indexing.

---

##  6. Parent-Child Indexing (Simulated Elasticsearch Behavior)

The assignment requires parent-child indexing for search.

Implemented using two in-memory structures:

### Parent index:

```
index_store = { planId → HealthPlan }
```

### Child index (by service name):

```
child_index_by_service_name = {
  "general consultation": [planId1, planId2]
}
```

`PATCH` and `DELETE` correctly update both parent and child indexes.

---

## 7. Search with Parent-Child Semantics

### ✔ `GET /search/by-service?service_name=...`

Returns all parent HealthPlans whose children contain a matching service name.

Imitates Elasticsearch parent-child join query.

---

##  8. Queueing (Assignment Requirement)

`PATCH` does not update the index immediately.

Instead, it schedules:

```
background_tasks.add_task(build_index_for_plan, updated_plan)
```

Using FastAPI’s **BackgroundTasks**, which simulates a queue worker.

This demonstrates the **asynchronous index update** requirement.

---

##  9. Security (Assignment Requirement)

Security implemented via Bearer Token:

### ✔ `/token`

Returns fixed demo token:

```json
{ "token": "demo-token" }
```

### ✔ All other operations

Require:

```
Authorization: Bearer demo-token
```

Unauthorized requests return `401`.

---

# ▶ How to Run the Application

```bash
uvicorn app:app --reload --port 8000
```

Root endpoint:

```
GET http://localhost:8000/
```

---

# ▶ Postman Testing (Full Demo Workflow)

The included Postman Collection demonstrates:

1. **Token retrieval**
2. **POST create** (validated JSON)
3. **GET by ID**
4. **PATCH with deep merge**
5. **PATCH conflict (If-Match mismatch)**
6. **Search (parent-child)**
7. **DELETE + cascaded delete**
8. **DELETE again → 404 (correct REST semantics)**

These steps provide full observable evidence for all required behaviors.

---

#  Conclusion

This implementation fulfills **all** Demo 3 specifications:

* Structured JSON API
* CRUD
* Merge semantics
* Validation
* Advanced update semantics
* KV storage
* Parent-child indexing
* Parent-child search
* Queueing / background tasks
* Security layer






```
