"""
Workflow Routes - Kuryos Beauty ERP v3.0
========================================

Public API for the workflow engine:
- /api/workflow/tasks                          (list, filter by entity, status, responsible)
- /api/workflow/tasks/{id}                     (get one)
- /api/workflow/tasks                          (POST create custom task)
- /api/workflow/tasks/{id}                     (PUT update — title, due_date, responsible, status)
- /api/workflow/tasks/{id}/complete            (PUT mark as completed)
- /api/workflow/tasks/by-entity/{type}/{id}    (list tasks for an entity)
- /api/workflow/audit-logs                     (list, filter by entity/user/action)
- /api/workflow/audit-logs/by-entity/{type}/{id} (entity history)
- /api/workflow/admin/reset-data               (admin: wipe operational data — KEEPS users/tenants/configs)
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional
import logging

import database as pg_db
from workflow_engine import (
    audit_log,
    list_audit_logs,
    list_tasks_filtered,
    list_tasks_for_entity,
    create_workflow_task,
    complete_task,
    create_user_notification,
    decide_task,
    ENTITY_TYPES,
    TASK_STATUSES,
    TASK_TYPES,
)

logger = logging.getLogger(__name__)

workflow_router = APIRouter(prefix="/api/workflow")


def _row(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d

# Module state
db = None
_get_current_user = None
_new_id = None
_now_iso = None


def init_workflow_routes(database, get_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Workflow routes initialized")


# ======================================================================
#   MODELS
# ======================================================================

class TaskCreateInput(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    description: str = ""
    category: str = "manual"
    blocking: bool = False
    blocks_stages: List[str] = []
    due_in_days: int = 3
    responsible_id: Optional[str] = None
    task_type: str = "standard"
    priority: str = "normal"


class TaskUpdateInput(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    responsible_id: Optional[str] = None
    assignment_reason: Optional[str] = None
    status: Optional[str] = None
    blocking: Optional[bool] = None


class TaskCompleteInput(BaseModel):
    comment: str = ""


class TaskDecisionInput(BaseModel):
    decision: str
    comment: str = ""


# ======================================================================
#   TASKS
# ======================================================================

@workflow_router.get("/tasks")
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    responsible_id: Optional[str] = None,
    blocking: Optional[bool] = None,
    mine: Optional[bool] = False,
    overdue: Optional[bool] = None,
    due_within_days: Optional[int] = Query(None, ge=0, le=30),
    task_type: Optional[str] = None,
):
    user = await _get_current_user(request)
    rid = user["id"] if mine else responsible_id
    tasks = await list_tasks_filtered(
        user["tenant_id"],
        status=status,
        responsible_id=rid,
        entity_type=entity_type,
        blocking=blocking,
        overdue=overdue,
        due_within_days=due_within_days,
        task_type=task_type,
    )
    return tasks


@workflow_router.get("/tasks/by-entity/{entity_type}/{entity_id}")
async def tasks_by_entity(entity_type: str, entity_id: str, request: Request):
    user = await _get_current_user(request)
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type inválido: {entity_type}")
    return await list_tasks_for_entity(user["tenant_id"], entity_type, entity_id)


@workflow_router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    user = await _get_current_user(request)
    task = _row(await pg_db.fetch_one(
        "SELECT * FROM workflow_tasks WHERE id=$1 AND tenant_id=$2",
        task_id, user["tenant_id"],
    ))
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return task


@workflow_router.post("/tasks")
async def create_task(data: TaskCreateInput, request: Request):
    user = await _get_current_user(request)
    if data.task_type not in TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"task_type inválido: {data.task_type}")
    if data.entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type inválido: {data.entity_type}")
    task = await create_workflow_task(
        tenant_id=user["tenant_id"],
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        title=data.title,
        description=data.description,
        category=data.category,
        blocking=data.blocking,
        blocks_stages=data.blocks_stages,
        due_in_days=data.due_in_days,
        responsible_id=data.responsible_id,
        created_by=user,
        metadata={"trigger": "manual", "task_type": data.task_type, "priority": data.priority},
    )
    return task


@workflow_router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdateInput, request: Request):
    user = await _get_current_user(request)
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM workflow_tasks WHERE id=$1 AND tenant_id=$2",
        task_id, user["tenant_id"],
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    assignment_reason = updates.pop("assignment_reason", None)
    if not updates:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    if existing.get("status") == "concluida":
        raise HTTPException(status_code=400, detail="Registro de conclusao e imutavel. Tarefas concluidas nao podem ser alteradas.")
    if "status" in updates and updates["status"] == "concluida":
        raise HTTPException(status_code=400, detail="Use o endpoint de conclusao ou decisao formal para fechar a tarefa.")
    if "status" in updates and updates["status"] not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido: {updates['status']}")

    if "responsible_id" in updates:
        u = _row(await pg_db.fetch_one(
            "SELECT id, name, role FROM users WHERE id=$1 AND tenant_id=$2",
            updates["responsible_id"], user["tenant_id"],
        ))
        updates["responsible_name"] = (u or {}).get("name", "")
        if updates["responsible_id"] != existing.get("responsible_id"):
            if not assignment_reason:
                raise HTTPException(status_code=400, detail="Informe o motivo do repasse da tarefa.")
            current_role = None
            if existing.get("responsible_id"):
                cur = _row(await pg_db.fetch_one(
                    "SELECT role FROM users WHERE id=$1 AND tenant_id=$2",
                    existing["responsible_id"], user["tenant_id"],
                ))
                current_role = (cur or {}).get("role")
            new_role = (u or {}).get("role")
            if current_role and new_role and current_role != new_role:
                raise HTTPException(status_code=400, detail="O repasse de tarefa so pode ocorrer entre usuarios do mesmo perfil.")
            history = list(existing.get("assignment_history") or [])
            history.append({
                "responsible_id": updates["responsible_id"],
                "responsible_name": updates["responsible_name"],
                "assigned_by": user["id"],
                "assigned_by_name": user.get("name", ""),
                "assigned_at": _now_iso(),
                "reason": assignment_reason or "manual_reassignment",
            })
            updates["assignment_history"] = history

    updates["updated_at"] = _now_iso()
    ALLOWED = {"title", "description", "due_date", "responsible_id", "responsible_name",
               "assignment_history", "status", "blocking"}
    set_parts = []
    params: list = []
    idx = 1
    for k, v in updates.items():
        if k not in ALLOWED:
            continue
        set_parts.append(f"{k}=${idx}")
        params.append(v)
        idx += 1
    set_parts.append(f"updated_at=${idx}")
    params.append(updates["updated_at"])
    idx += 1
    params.extend([task_id, user["tenant_id"]])
    await pg_db.execute(
        f"UPDATE workflow_tasks SET {', '.join(set_parts)} WHERE id=${idx} AND tenant_id=${idx+1}",
        *params,
    )

    if "responsible_id" in updates and updates["responsible_id"] != existing.get("responsible_id"):
        await create_user_notification(
            tenant_id=user["tenant_id"],
            user_id=updates["responsible_id"],
            title=f"Tarefa repassada: {existing.get('title', '')}",
            message=f"{user.get('name', '')} atribuiu esta tarefa para voce.",
            entity_type=existing.get("entity_type", ""),
            entity_id=existing.get("entity_id", ""),
            metadata={"task_id": task_id, "entity_type": existing.get("entity_type"), "entity_id": existing.get("entity_id")},
        )

    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="task_updated",
        entity_type="workflow_task",
        entity_id=task_id,
        before={k: existing.get(k) for k in updates if k != "updated_at"},
        after=updates,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM workflow_tasks WHERE id=$1", task_id))


@workflow_router.put("/tasks/{task_id}/complete")
async def mark_task_complete(task_id: str, data: TaskCompleteInput, request: Request):
    user = await _get_current_user(request)
    return await complete_task(
        tenant_id=user["tenant_id"], task_id=task_id, user=user, comment=data.comment
    )


@workflow_router.put("/tasks/{task_id}/decision")
async def decide_workflow_task(task_id: str, data: TaskDecisionInput, request: Request):
    user = await _get_current_user(request)
    return await decide_task(
        tenant_id=user["tenant_id"],
        task_id=task_id,
        user=user,
        decision=data.decision,
        comment=data.comment,
    )


@workflow_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, request: Request):
    user = await _get_current_user(request)
    if user.get("role") not in ("admin", "gestor", "lider_pd", "sales_ops"):
        raise HTTPException(status_code=403, detail="Apenas admin/lider_pd/sales_ops podem excluir tarefas")
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM workflow_tasks WHERE id=$1 AND tenant_id=$2",
        task_id, user["tenant_id"],
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    await pg_db.execute(
        "DELETE FROM workflow_tasks WHERE id=$1 AND tenant_id=$2",
        task_id, user["tenant_id"],
    )
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="task_deleted",
        entity_type="workflow_task",
        entity_id=task_id,
        before=existing,
    )
    return {"message": "Tarefa removida"}


# ======================================================================
#   AUDIT LOG
# ======================================================================

@workflow_router.get("/audit-logs")
async def get_audit_logs(
    request: Request,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    user = await _get_current_user(request)
    if user.get("role") not in ("admin", "gestor", "lider_pd", "sales_ops", "qa"):
        raise HTTPException(status_code=403, detail="Apenas admin/gestor/lider_pd/sales_ops/qa podem visualizar audit log")
    return await list_audit_logs(
        user["tenant_id"],
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        limit=limit,
    )


@workflow_router.get("/audit-logs/by-entity/{entity_type}/{entity_id}")
async def get_entity_audit(entity_type: str, entity_id: str, request: Request):
    user = await _get_current_user(request)
    return await list_audit_logs(
        user["tenant_id"],
        entity_type=entity_type,
        entity_id=entity_id,
        limit=500,
    )


# ======================================================================
#   TASK REMINDERS + ESCALATION (D-1 notifications + auto-escalation)
# ======================================================================

@workflow_router.post("/tasks/check-reminders")
async def check_task_reminders(request: Request):
    """Checks for D-1 reminders and auto-escalation for overdue blocking tasks."""
    user = await _get_current_user(request)
    now = datetime.now(timezone.utc)
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # D-1: tasks due tomorrow not yet reminded
    d1_tasks = [dict(r) for r in await pg_db.fetch_all(
        """SELECT id, title, due_date, entity_type, entity_id, responsible_id
           FROM workflow_tasks
           WHERE tenant_id=$1 AND status IN ('pendente', 'em_andamento')
             AND due_date >= $2 AND due_date < $3
             AND (d1_notified IS NULL OR d1_notified = FALSE)""",
        user["tenant_id"], tomorrow_start.isoformat(), tomorrow_end.isoformat(),
    )]

    notified_count = 0
    for task in d1_tasks:
        if task.get("responsible_id"):
            await create_user_notification(
                tenant_id=user["tenant_id"],
                user_id=task["responsible_id"],
                title=f"Lembrete D-1: {task['title']}",
                message=f"Vence amanhã ({(task.get('due_date') or '')[:10]}). Entidade: {task.get('entity_type','')}/{(task.get('entity_id') or '')[:8]}",
                notif_type="d1_reminder",
                entity_type=task.get("entity_type", ""),
                entity_id=task.get("entity_id", ""),
            )
        await pg_db.execute(
            "UPDATE workflow_tasks SET d1_notified=TRUE WHERE id=$1",
            task["id"],
        )
        notified_count += 1

    # Escalation: blocking tasks overdue > 3 days, not yet escalated
    cutoff_3d = (now - timedelta(days=3)).isoformat()
    overdue_tasks = [dict(r) for r in await pg_db.fetch_all(
        """SELECT id FROM workflow_tasks
           WHERE tenant_id=$1 AND status IN ('pendente', 'em_andamento')
             AND due_date < $2
             AND (escalated IS NULL OR escalated = FALSE)
             AND blocking = TRUE""",
        user["tenant_id"], cutoff_3d,
    )]

    escalated_count = 0
    for task in overdue_tasks:
        await pg_db.execute(
            "UPDATE workflow_tasks SET escalated=TRUE, escalated_at=$1, updated_at=NOW() WHERE id=$2",
            now.isoformat(), task["id"],
        )
        escalated_count += 1

    return {"d1_notified": notified_count, "escalated": escalated_count, "checked_at": now.isoformat()}


# ======================================================================
#   ADMIN: RESET OPERATIONAL DATA
# ======================================================================

@workflow_router.post("/admin/reset-data")
async def reset_operational_data(request: Request):
    """Wipes operational entities for the current tenant.
    Keeps: users, tenants, pipelines, stages, fields, crm_*_configs.
    Removes: clients, projects, samples, pd_cards, skus, tasks, audit_logs, alerts, counters,
             pd_requests/developments/formulas/tests/samples/approvals/costs/documents,
             messages, notifications, files, email_logs.
    """
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Somente admin pode resetar dados")

    tid = user["tenant_id"]
    deletions = {}

    # PostgreSQL tables (migrated)
    pg_tables = [
        "crm_clients", "crm_projects", "crm_samples", "skus", "crm_alerts",
        "crm_column_configs", "crm_field_configs", "lead_sources",
        "workflow_tasks", "audit_logs", "notifications",
        "contratos", "order_material_requirements",
        "pd_cards", "pd_requests", "pd_document_versions",
        # 7.2 migrated:
        "retrabalho_ordens", "recebimentos", "recebimento_sla_config",
        "estoque_movimentos", "estoque_items",
        "expedicao_ordens", "propostas_comerciais",
        # 7.3 migrated:
        "faturamento_notas", "faturamento_duplicatas",
        "pcp_lotes", "pcp_programacao", "pcp_calendario", "pcp_linhas",
        "produtos_pai", "bom_items",
    ]
    for tbl in pg_tables:
        try:
            await pg_db.execute(f"DELETE FROM {tbl} WHERE tenant_id=$1", tid)
            deletions[f"pg_{tbl}"] = "ok"
        except Exception as e:
            deletions[f"pg_{tbl}"] = f"err: {e}"

    await pg_db.execute(
        "DELETE FROM counters WHERE id LIKE $1",
        f"%:{tid}",
    )
    deletions["pg_counters"] = "ok"

    # MongoDB collections not yet migrated
    mongo_collections = [
        "tasks", "messages", "card_history", "card_products",
        "field_values", "cards",
        "homologacao_mps", "homologacao_fornecedores",
        "files", "email_logs", "orders",
        "kickoffs", "pd_ficha_tecnica",
    ]
    for col in mongo_collections:
        try:
            res = await db[col].delete_many({"tenant_id": tid})
            deletions[col] = res.deleted_count
        except Exception as e:  # pragma: no cover
            deletions[col] = f"err: {e}"

    await audit_log(
        tenant_id=tid,
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="tenant_data_reset",
        entity_type="tenant",
        entity_id=tid,
        metadata={"deletions": deletions},
    )
    return {"message": "Dados operacionais resetados", "deletions": deletions}
