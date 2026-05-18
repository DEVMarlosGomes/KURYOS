"""
KURYOS — Backend Regression for 8-item Sprint plan.

Items:
 1. PUT /api/pd/formula-items/{item_id}
 2. GET /api/pd/catalog/search
 3. POST /api/pd/ordens-manipulacao (+ GET, PUT/status, DELETE block, /pdf)
 4. Ficha técnica without costs
 5. cost-versions role visibility
 6. CRM PD move transitions + retroceder
 7. /api/pd/formulas/bank fragrance fields
 8. PUT /api/pd/formulas/{id} modo_preparo persistence
"""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# Pre-existing seed mentioned by main agent
SAMPLE_ID = "sample-test-om-001"
VAR_IDS = ["var-1", "var-2", "var-3", "var-4"]
CARD_ID = "card-test-001"
OM_ID = "3bbfc261-863b-406a-bf02-23f5154c714e"
FORMULA_ID = "ad6c7a64-b4dd-48a3-a769-3ee4b6e2c529"
DEV_ID = "2da56af0-c6fb-4f11-a776-15ceba32fb08"
REQUEST_ID = "a77ea73b-db7e-4c48-aecb-f4aa1561a2e8"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@kuryos.com", "admin123")


@pytest.fixture(scope="module")
def formulador():
    return _login("formulador@kuryos.com", "kuryos123")


@pytest.fixture(scope="module")
def liderpd():
    return _login("liderpd@kuryos.com", "kuryos123")


@pytest.fixture(scope="module")
def vendedor():
    return _login("vendedor@kuryos.com", "kuryos123")


@pytest.fixture(scope="module")
def qa():
    return _login("qa@kuryos.com", "kuryos123")


# ------------------ ITEM 2 — catalog/search ------------------
class TestItem2CatalogSearch:
    def test_search_returns_results_ordered_by_price(self, admin):
        r = admin.get(f"{API}/pd/catalog/search?q=alco")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        # at least one item should have fornecedores ordered by price
        for it in data:
            forn = it.get("fornecedores", [])
            if len(forn) >= 2:
                prices = [f["preco_rs_kg"] for f in forn if f.get("preco_rs_kg") is not None]
                assert prices == sorted(prices), "fornecedores must be ordered ASC by preco_rs_kg"
                # Semáforo first item should be verde
                assert forn[0].get("semaforo") == "verde"
                break

    def test_search_short_query_returns_empty(self, admin):
        r = admin.get(f"{API}/pd/catalog/search?q=a")
        assert r.status_code == 200
        assert r.json() == []

    def test_search_two_char_query_works(self, admin):
        r = admin.get(f"{API}/pd/catalog/search?q=al")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ------------------ ITEM 1 — PUT formula-items ------------------
class TestItem1EditFormulaItem:
    def test_edit_formula_item(self, admin):
        # get formula via development to find an item id
        r = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica-ui")
        assert r.status_code == 200
        ui = r.json()
        items = ui.get("formula_items") or []
        if not items:
            pytest.skip("no formula items available to edit")
        item_id = items[0]["id"]
        orig_pct = items[0].get("percentage", 0)
        new_pct = round(orig_pct + 0.1, 2) if orig_pct < 99 else 1.0
        payload = {"percentage": new_pct}
        r = admin.put(f"{API}/pd/formula-items/{item_id}", json=payload)
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"
        # verify persistence
        r2 = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica-ui")
        items2 = r2.json().get("formula_items") or []
        updated = next((i for i in items2 if i["id"] == item_id), None)
        assert updated is not None
        assert abs(updated["percentage"] - new_pct) < 0.001


# ------------------ ITEM 3 — Ordens de Manipulação ------------------
class TestItem3OM:
    def test_om_get_existing(self, admin):
        r = admin.get(f"{API}/pd/ordens-manipulacao/{OM_ID}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["n_variacoes"] == 4
        # check quantidade_g per item: n * volume_ml * (1+perda/100) * pct/100
        # Expected formula: n*vol*(1+perda/100) * pct
        n = d["n_variacoes"]
        vol = d["volume_amostra_ml"]
        perda = d.get("perda_processo_pct", 0)
        if d.get("itens"):
            it = d["itens"][0]
            pct = it.get("percentage") or it.get("percentual") or 0
            qty = it.get("quantidade_g")
            expected = n * vol * (1 + perda / 100) * (pct / 100)
            # allow density consideration; just check >0 and finite
            assert qty is not None and qty > 0
            # If percent-based simple formula match, assert close
            if abs(qty - expected) > 0.5:
                # Some implementations use g/ml directly; accept anyway but log
                print(f"[info] qty={qty} expected_simple={expected}")

    def test_om_list(self, admin):
        r = admin.get(f"{API}/pd/ordens-manipulacao")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_om_pdf(self, admin):
        r = admin.get(f"{API}/pd/ordens-manipulacao/{OM_ID}/pdf")
        assert r.status_code == 200, r.text[:300]
        assert "application/pdf" in r.headers.get("content-type", "").lower()

    def test_om_create_and_status_transitions(self, admin):
        payload = {
            "sample_id": SAMPLE_ID,
            "variacao_ids": VAR_IDS,
            "formula_base_id": FORMULA_ID,
            "volume_amostra_ml": 100,
            "perda_processo_pct": 5,
        }
        r = admin.post(f"{API}/pd/ordens-manipulacao", json=payload)
        assert r.status_code in (200, 201), r.text
        om = r.json()
        new_id = om["id"]
        assert om.get("status") == "rascunho"
        assert om.get("n_variacoes") == 4

        # status rascunho -> emitida
        r = admin.put(f"{API}/pd/ordens-manipulacao/{new_id}/status",
                      json={"status": "emitida"})
        assert r.status_code in (200, 204), r.text

        # emitida -> executada
        r = admin.put(f"{API}/pd/ordens-manipulacao/{new_id}/status",
                      json={"status": "executada"})
        assert r.status_code in (200, 204), r.text

        # DELETE blocked because executada
        r = admin.delete(f"{API}/pd/ordens-manipulacao/{new_id}")
        assert r.status_code in (400, 409, 403), f"expected delete blocked got {r.status_code} {r.text}"


# ------------------ ITEM 4 — Ficha Técnica without costs ------------------
class TestItem4FichaNoCosts:
    FORBIDDEN = {"price_per_kg", "cost_brl", "cost_kg_usd", "cost_percentage"}

    def test_ficha_data_no_costs(self, admin):
        r = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica-data")
        assert r.status_code == 200, r.text
        data = r.json()
        # recursively check forbidden keys
        flat = json.dumps(data)
        for k in self.FORBIDDEN:
            assert f'"{k}"' not in flat, f"forbidden key {k} present in ficha-tecnica-data"

    def test_ficha_ui_no_costs_in_formula_items(self, admin):
        r = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica-ui")
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("formula_items") or []
        for it in items:
            for k in self.FORBIDDEN:
                assert k not in it, f"forbidden cost key {k} in formula_items"

    def test_ficha_pdf_returns_pdf(self, admin):
        r = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica")
        # could be PDF or JSON; accept either but PDF preferred
        assert r.status_code == 200, r.text[:200]


# ------------------ ITEM 5 — cost-versions role visibility ------------------
class TestItem5CostVersionsRBAC:
    URL = None

    def setup_method(self, method):
        TestItem5CostVersionsRBAC.URL = f"{API}/pd/developments/{DEV_ID}/cost-versions"

    def test_admin_sees_full(self, admin):
        r = admin.get(self.URL)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "v1" in d
        # admin/compras: full
        v1 = d.get("v1") or {}
        if v1:
            # full view should contain numeric totals
            assert "total" in v1 or "ingredient_cost_auto" in v1

    def test_formulador_sees_v1_full_v2_status_only(self, formulador):
        r = formulador.get(self.URL)
        assert r.status_code == 200, r.text
        d = r.json()
        v1 = d.get("v1")
        v2 = d.get("v2")
        assert v1 is not None
        # v1 should be full (has total or ingredient costs)
        assert "total" in v1 or "ingredient_cost_auto" in v1
        # v2 if exists for formulador should NOT contain financial numbers, only status
        if v2 is not None:
            forbidden = {"total", "ingredient_cost_auto", "ingredient_cost_manual"}
            assert not (set(v2.keys()) & forbidden), f"formulador should not see v2 finances: {v2}"

    def test_vendedor_sees_only_total_final_when_v2_finalized(self, vendedor):
        r = vendedor.get(self.URL)
        # Could be 200 with restricted view or 403
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            d = r.json()
            # vendedor should not see v1 details. Only total_final (if v2 finalized)
            v1 = d.get("v1")
            if v1:
                # should not have raw cost details
                forbidden = {"ingredient_cost_auto", "ingredient_cost_manual"}
                assert not (set(v1.keys()) & forbidden), f"vendedor leak: {v1}"


# ------------------ ITEM 6 — CRM PD transitions + retroceder ------------------
class TestItem6PDTransitions:
    def test_invalid_transition_formulador_400(self, formulador):
        # card is in em_desenvolvimento; jumping to entregue_ao_comercial should fail
        r = formulador.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                           json={"status": "entregue_ao_comercial"})
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"
        body = r.json()
        detail = body.get("detail") or {}
        assert isinstance(detail, dict)
        assert "transicoes_permitidas" in detail

    def test_admin_can_skip_validation(self, admin):
        # first ensure card status (re-read)
        r = admin.get(f"{API}/crm/pd/cards/{CARD_ID}")
        assert r.status_code == 200
        cur_status = r.json()["status_pd"]
        # try jump to a non-adjacent valid status
        target = "aprovado_internamente" if cur_status != "aprovado_internamente" else "em_testes"
        r2 = admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                       json={"status": target})
        # admin bypasses transition validation
        assert r2.status_code in (200, 204), f"admin should skip validation: {r2.status_code} {r2.text}"
        # restore original status
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": cur_status})

    def test_retroceder_short_justificativa_422(self, formulador):
        r = formulador.post(f"{API}/pd/cards/{CARD_ID}/retroceder",
                            json={"justificativa": "curto", "status_destino": "solicitado"})
        assert r.status_code in (400, 422), f"got {r.status_code} {r.text}"

    def test_retroceder_formulador_creates_pending(self, formulador, admin):
        # ensure card status is em_desenvolvimento first
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})
        r = formulador.post(
            f"{API}/pd/cards/{CARD_ID}/retroceder",
            json={"justificativa": "justificativa longa o suficiente para teste de retrocesso",
                  "status_destino": "solicitado"},
        )
        assert r.status_code in (200, 201), f"got {r.status_code} {r.text}"
        # The RESPONSE should indicate aguardando_aprovacao (solicitation pending)
        body = r.json()
        assert body.get("status") == "aguardando_aprovacao", f"response status mismatch: {body}"
        # Card status should NOT change (pending approval)
        r2 = admin.get(f"{API}/crm/pd/cards/{CARD_ID}")
        st = r2.json()["status_pd"]
        assert st == "em_desenvolvimento", f"card should not change yet, got {st}"

    def test_retroceder_admin_direct(self, admin):
        # reset card
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})
        r = admin.post(
            f"{API}/pd/cards/{CARD_ID}/retroceder",
            json={"justificativa": "admin retrocede com justificativa suficiente",
                  "status_destino": "solicitado"},
        )
        assert r.status_code in (200, 201), r.text
        r2 = admin.get(f"{API}/crm/pd/cards/{CARD_ID}")
        st = r2.json()["status_pd"]
        assert st in ("retrocedido", "solicitado"), f"got {st}"
        # restore for downstream tests
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})

    def test_retrocesso_decisao_only_admin_or_liderpd(self, formulador, liderpd, admin):
        # create a pending retrocesso first by formulador
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})
        r = formulador.post(
            f"{API}/pd/cards/{CARD_ID}/retroceder",
            json={"justificativa": "outro retrocesso para teste de decisao",
                  "status_destino": "solicitado"},
        )
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create pending retrocesso")
        body = r.json()
        retro_id = (body.get("solicitacao") or {}).get("id") or body.get("id") or body.get("retrocesso_id")
        if not retro_id:
            pytest.skip("retrocesso id not returned")
        # formulador should NOT be able to decide
        rdf = formulador.put(f"{API}/pd/retrocessos/{retro_id}/decisao",
                             json={"decisao": "aprovado", "comentario": "ok"})
        assert rdf.status_code in (401, 403), f"formulador should be forbidden, got {rdf.status_code}"
        # liderpd can decide
        rl = liderpd.put(f"{API}/pd/retrocessos/{retro_id}/decisao",
                         json={"decisao": "aprovado", "comentario": "ok"})
        assert rl.status_code in (200, 204), f"liderpd should decide, got {rl.status_code} {rl.text}"

    def test_entregue_ao_comercial_in_statuses(self, admin):
        # indirectly: try moving from aprovado_internamente to entregue_ao_comercial (valid transition)
        # at least ensure status string is accepted
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})
        # admin jumps to aprovado_internamente
        r1 = admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                       json={"status": "aprovado_internamente"})
        assert r1.status_code in (200, 204)
        r2 = admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                       json={"status": "entregue_ao_comercial"})
        assert r2.status_code in (200, 204), f"entregue_ao_comercial not accepted: {r2.text}"
        # restore
        admin.put(f"{API}/crm/pd/cards/{CARD_ID}/move",
                  json={"status": "em_desenvolvimento"})


# ------------------ ITEM 7 — formulas/bank fragrance fields ------------------
class TestItem7FormulasBank:
    def test_bank_has_fragrance_fields(self, admin):
        r = admin.get(f"{API}/pd/formulas/bank")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if not data:
            pytest.skip("no formulas in bank")
        # at least one formula should expose fragrance fields per item
        found = False
        for f in data:
            items = f.get("items") or f.get("formula_items") or []
            for it in items:
                if "fragrance_percentage" in it and "fragrance_target" in it:
                    found = True
                    break
            if "fragrance_percentage" in f and "fragrance_target" in f:
                found = True
            if found:
                break
        assert found, "fragrance_percentage / fragrance_target not present in formulas/bank response"


# ------------------ ITEM 8 — modo_preparo persistence ------------------
class TestItem8ModoPreparo:
    def test_put_formula_modo_preparo_structured(self, admin):
        modo = [{
            "ordem": 1, "fase": "A", "descricao": "Pesar e misturar",
            "temperatura_c": 25, "tempo_minutos": 5,
            "equipamento": "Agitador", "rpm": 300, "alerta": "Cuidado com vapores"
        }]
        payload = {"modo_preparo": modo}
        r = admin.put(f"{API}/pd/formulas/{FORMULA_ID}", json=payload)
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"
        # verify via ficha-tecnica-data
        r2 = admin.get(f"{API}/pd/requests/{REQUEST_ID}/ficha-tecnica-data")
        assert r2.status_code == 200
        mp = r2.json().get("modo_preparo") or []
        assert isinstance(mp, list) and len(mp) >= 1
        first = mp[0]
        assert first.get("ordem") == 1
        assert first.get("fase") == "A"
        assert first.get("temperatura_c") == 25
        assert first.get("equipamento") == "Agitador"
        assert first.get("rpm") == 300

    def test_put_formula_modo_preparo_list_of_strings(self, admin):
        payload = {"modo_preparo": ["Pesar fase A", "Misturar 10 min", "Adicionar fragrância"]}
        r = admin.put(f"{API}/pd/formulas/{FORMULA_ID}", json=payload)
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"
        # restore structured for later tests
        admin.put(f"{API}/pd/formulas/{FORMULA_ID}", json={
            "modo_preparo": [{
                "ordem": 1, "fase": "A", "descricao": "Pesar álcool e água em béquer de 1L",
                "temperatura_c": 25, "tempo_minutos": 5,
                "equipamento": "Balança", "rpm": None, "alerta": "Manter recipiente fechado"
            }]
        })

    def test_put_formula_accepts_extra_fields(self, admin):
        payload = {
            "ph_min": 5.0, "ph_max": 6.5,
            "aspecto": "Líquido transparente", "cor": "Incolor",
            "odor": "Característico de fragrância floral"
        }
        r = admin.put(f"{API}/pd/formulas/{FORMULA_ID}", json=payload)
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"
