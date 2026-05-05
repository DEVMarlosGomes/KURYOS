import os
import sys
import asyncio

import pytest

sys.path.insert(0, os.path.abspath("backend"))

import workflow_engine
import pd_routes


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

    async def update_one(self, query, update):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, query):
                updated = dict(doc)
                for key, value in update.get("$set", {}).items():
                    self._set_nested(updated, key, value)
                self.docs[idx] = updated
                return FakeResult(matched_count=1)
        return FakeResult(matched_count=0)

    def _matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def _project(self, doc, projection):
        if projection is None:
            return dict(doc)
        if projection.get("_id") == 0:
            return {key: value for key, value in doc.items() if key != "_id"}
        return dict(doc)

    def _set_nested(self, doc, dotted_key, value):
        parts = dotted_key.split(".")
        current = doc
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value


class FakeDB:
    def __init__(self):
        self.workflow_tasks = FakeCollection([
            {
                "id": "task-1",
                "tenant_id": "tenant-1",
                "entity_type": "client",
                "entity_id": "client-1",
                "task_type": "approval",
                "status": "pendente",
                "responsible_id": "user-1",
                "responsible_name": "Reviewer",
                "created_by": "creator-1",
                "created_by_name": "Creator",
                "notification_flags": {},
            }
        ])
        self.audit_logs = FakeCollection()
        self.notifications = FakeCollection()


def test_decide_task_completes_approval_and_records_decision():
    fake_db = FakeDB()
    workflow_engine.db = fake_db
    workflow_engine._now_iso = lambda: "2026-04-28T12:00:00+00:00"
    workflow_engine._new_id = lambda: "log-1"

    updated = asyncio.run(
        workflow_engine.decide_task(
            tenant_id="tenant-1",
            task_id="task-1",
            user={"id": "user-1", "name": "Reviewer", "role": "gestor"},
            decision="approved",
            comment="Liberado",
        )
    )

    assert updated["status"] == "concluida"
    assert updated["decision"] == "approved"
    assert updated["completed_by"] == "user-1"
    assert fake_db.audit_logs.docs
    assert fake_db.notifications.docs


def test_stability_templates_and_parameter_normalization_follow_spec_baseline():
    conditions = pd_routes._build_stability_conditions("2026-04-28T12:00:00+00:00")
    normalized = pd_routes._normalize_stability_parameters(
        {"appearance": "ok", "pH": 6.2, "invalid_field": "ignored"}
    )

    assert len(conditions) == 9
    assert all(condition["checkpoints"][0] == 0 for condition in conditions)
    assert normalized == {"appearance": "ok", "ph": 6.2}
