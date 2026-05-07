"""
Backend tests for Orders (Pedidos) module.
Covers CRUD, PDF generation, RBAC, and PD->Order auto-creation idempotency.
Auth: cookie-based session (POST /api/auth/login sets cookies).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

PD_TEST_ID = "c04daf64-da3a-4e86-b6d9-04e917209adc"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login("admin@kuryos.com", "admin123")


@pytest.fixture(scope="session")
def vendedor():
    return _login("vendedor@kuryos.com", "kuryos123")


@pytest.fixture(scope="session")
def formulador():
    return _login("formulador@kuryos.com", "kuryos123")


# ===== List & RBAC =====
class TestListOrdersRBAC:
    def test_admin_can_list(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_vendedor_can_list(self, vendedor):
        r = vendedor.get(f"{BASE_URL}/api/orders", timeout=15)
        assert r.status_code == 200

    def test_formulador_can_list(self, formulador):
        r = formulador.get(f"{BASE_URL}/api/orders", timeout=15)
        assert r.status_code == 200

    def test_unauthenticated_blocked(self):
        r = requests.get(f"{BASE_URL}/api/orders", timeout=15)
        assert r.status_code in (401, 403)


# ===== Auto-create from PD APPROVED =====
class TestAutoCreatedOrder:
    def test_auto_created_order_exists(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders", timeout=15)
        assert r.status_code == 200
        orders = r.json()
        matches = [o for o in orders if o.get("pd_request_id") == PD_TEST_ID]
        assert len(matches) >= 1, f"Expected auto-created order for PD {PD_TEST_ID}"
        order = matches[0]
        assert order.get("client_card_id"), "client_card_id should be populated"
        assert order.get("auto_created") is True
        assert order.get("numero_pedido"), "numero_pedido should be set"
        assert len(order.get("items", [])) >= 1
        cliente = order.get("cliente", {})
        assert cliente.get("nome") or cliente.get("razao_social")

    def test_idempotency_no_duplicates(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders", timeout=15)
        orders = r.json()
        matches = [o for o in orders if o.get("pd_request_id") == PD_TEST_ID]
        assert len(matches) == 1, f"Idempotency violated: {len(matches)} orders for PD {PD_TEST_ID}"


# ===== Get single order =====
class TestGetOrder:
    def test_get_existing_order(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders", timeout=15)
        orders = r.json()
        if not orders:
            pytest.skip("No orders to test GET")
        oid = orders[0]["id"]
        r2 = admin.get(f"{BASE_URL}/api/orders/{oid}", timeout=15)
        assert r2.status_code == 200
        d = r2.json()
        assert d["id"] == oid
        for key in ("cliente", "frete", "items", "condicoes", "insumos", "status"):
            assert key in d

    def test_get_nonexistent(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders/does-not-exist-xyz", timeout=15)
        assert r.status_code == 404


# ===== CRUD =====
class TestOrderCRUD:
    created_id = None

    def test_create_order(self, admin):
        payload = {
            "numero_pedido": "TEST_99_99",
            "cliente": {
                "nome": "TEST Client",
                "razao_social": "TEST LTDA",
                "cnpj": "00.000.000/0001-00",
            },
            "items": [
                {"item": "Produto A", "valor_unitario": 10.5, "qtd": 3},
                {"item": "Produto B", "valor_unitario": 20.0, "qtd": 2},
            ],
        }
        r = admin.post(f"{BASE_URL}/api/orders", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cliente"]["nome"] == "TEST Client"
        assert data["total_pedido"] == 71.5
        assert data["status"] == "rascunho"
        TestOrderCRUD.created_id = data["id"]

    def test_get_created(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.get(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}", timeout=15)
        assert r.status_code == 200
        assert r.json()["numero_pedido"] == "TEST_99_99"

    def test_update_status(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.put(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}",
                      json={"status": "confirmado"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "confirmado"

    def test_update_invalid_status(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.put(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}",
                      json={"status": "INVALID_XYZ"}, timeout=15)
        assert r.status_code == 400

    def test_update_items_recalculates_total(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        new_items = [{"item": "X", "valor_unitario": 5.0, "qtd": 4}]
        r = admin.put(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}",
                      json={"items": new_items}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total_pedido"] == 20.0
        assert len(d["items"]) == 1

    def test_pdf_generation(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.get(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}/pdf", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000

    def test_pdf_for_auto_created(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders", timeout=15)
        orders = r.json()
        matches = [o for o in orders if o.get("pd_request_id") == PD_TEST_ID]
        if not matches:
            pytest.skip("Auto-created order not present")
        oid = matches[0]["id"]
        r2 = admin.get(f"{BASE_URL}/api/orders/{oid}/pdf", timeout=30)
        assert r2.status_code == 200
        assert r2.content[:4] == b"%PDF"

    def test_delete_order(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.delete(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}", timeout=15)
        assert r.status_code == 200

    def test_get_after_delete_404(self, admin):
        if not TestOrderCRUD.created_id:
            pytest.skip("Create failed")
        r = admin.get(f"{BASE_URL}/api/orders/{TestOrderCRUD.created_id}", timeout=15)
        assert r.status_code == 404


# ===== Filters / search =====
class TestFilters:
    def test_status_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders?status=rascunho", timeout=15)
        assert r.status_code == 200
        for o in r.json():
            assert o.get("status") == "rascunho"

    def test_search_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/orders?q=05", timeout=15)
        assert r.status_code == 200
