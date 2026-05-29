import asyncio
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath("backend"))

import crm_routes


class FakeResult:
    def __init__(self, matched_count=1, deleted_count=0):
        self.matched_count = matched_count
        self.deleted_count = deleted_count


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return FakeResult()

    async def delete_many(self, query):
        kept = []
        deleted = 0
        for doc in self.docs:
            if self._matches(doc, query):
                deleted += 1
            else:
                kept.append(doc)
        self.docs = kept
        return FakeResult(deleted_count=deleted)

    def _matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict):
                if "$in" in value and doc.get(key) not in value["$in"]:
                    return False
                if "$ne" in value and doc.get(key) == value["$ne"]:
                    return False
                continue
            if doc.get(key) != value:
                return False
        return True

    def _project(self, doc, projection):
        if projection is None:
            return dict(doc)
        if projection.get("_id") == 0:
            return {key: value for key, value in doc.items() if key != "_id"}
        return dict(doc)


class FakeDB:
    def __init__(self):
        self.crm_clients = FakeCollection()
        self.users = FakeCollection([
            {"id": "user-1", "tenant_id": "tenant-1", "name": "Tester"}
        ])
        self.crm_projects = FakeCollection()
        self.workflow_tasks = FakeCollection()
        self.audit_logs = FakeCollection()


def _base_client_payload(canal_origem):
    return {
        "nome_empresa": "Cliente Teste",
        "cnpj": "",
        "contato_principal": {
            "nome": "Contato Teste",
            "whatsapp": "11999999999",
            "email": "contato@example.com",
        },
        "contatos_adicionais": [],
        "canal_origem": canal_origem,
        "categoria_interesse": ["hidratante_facial"],
        "origem_lead": "site",
        "temperatura_lead": "morno",
        "responsavel_comercial": "user-1",
        "segmento": "outro",
        "porte": "medio",
        "regiao": "SP",
        "site": "",
        "instagram": "",
        "observacoes": "",
    }


def test_validate_client_payload_accepts_all_canal_origem_values():
    fake_db = FakeDB()
    crm_routes.db = fake_db

    for option in crm_routes.CANAL_ORIGEM_OPTIONS:
        payload = _base_client_payload(option)
        validated = asyncio.run(
            crm_routes._validate_client_payload("tenant-1", payload)
        )
        assert validated["canal_origem"] == option


def test_validate_client_payload_rejects_invalid_canal_origem():
    fake_db = FakeDB()
    crm_routes.db = fake_db

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            crm_routes._validate_client_payload(
                "tenant-1",
                _base_client_payload("instagram"),
            )
        )

    assert exc_info.value.status_code == 400
    assert "Canal de origem" in str(exc_info.value.detail)


def test_batch_create_projects_rolls_back_when_secondary_step_fails(monkeypatch):
    fake_db = FakeDB()
    crm_routes.db = fake_db

    async def fake_get_current_user(_request):
        return {
            "id": "user-1",
            "name": "Tester",
            "tenant_id": "tenant-1",
            "role": "admin",
        }

    async def fake_assert_client_exists(_tenant_id, _client_id):
        return {
            "id": "client-1",
            "tenant_id": "tenant-1",
            "nome_empresa": "Cliente Teste",
            "responsavel_comercial": "user-1",
        }

    async def fake_create_workflow_task(**_kwargs):
        task = {"id": "task-1", "tenant_id": "tenant-1"}
        await fake_db.workflow_tasks.insert_one(task)
        return task

    async def failing_deadline_task(_project, _user):
        raise RuntimeError("deadline failed")

    monkeypatch.setattr(crm_routes, "_get_current_user", fake_get_current_user)
    monkeypatch.setattr(crm_routes, "require_roles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(crm_routes, "assert_client_exists", fake_assert_client_exists)
    monkeypatch.setattr(crm_routes, "create_workflow_task", fake_create_workflow_task)
    monkeypatch.setattr(crm_routes, "_create_project_deadline_alert_task", failing_deadline_task)
    monkeypatch.setattr(crm_routes, "_new_id", lambda: "project-1")
    monkeypatch.setattr(crm_routes, "_now_iso", lambda: "2026-05-22T12:00:00+00:00")

    payload = crm_routes.ProjectBatchCreate(
        cliente_id="client-1",
        projects=[crm_routes.ProjectBatchItem(nome_projeto="Projeto Teste")],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(crm_routes.batch_create_projects(payload, SimpleNamespace()))

    assert exc_info.value.status_code == 500
    assert fake_db.crm_projects.docs == []
    assert fake_db.workflow_tasks.docs == []
    assert fake_db.audit_logs.docs == []
