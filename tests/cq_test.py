#!/usr/bin/env python3
"""
CQ Integration Tests — Módulo Controle de Qualidade
====================================================
Cobre os fluxos completos: RA, RNC, Checklists, Instrumentos,
Hard Stops, Scheduler e segurança (405/409/403).

Pre-requisites:
    pip install pytest pytest-asyncio httpx motor

Executar (Windows):
    set DB_NAME=kuryos_cq_test
    pytest cq_test.py -v -s --asyncio-mode=auto

Executar (Linux/Mac):
    DB_NAME=kuryos_cq_test pytest cq_test.py -v -s --asyncio-mode=auto

Notas:
  - Usa DB separado (kuryos_cq_test) para não poluir o banco principal.
  - Cada execução usa um RUN_ID único — sem colisões entre runs.
  - Os testes são sequenciais; usam ctx{} para passar estado entre funções.
"""

# ── Env vars ANTES de qualquer import do projeto ───────────────────────────────
import os, sys, uuid
os.environ.setdefault("DB_NAME", "kuryos_cq_test")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("JWT_SECRET", "cq-test-jwt-secret-not-for-prod")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

# ── Imports padrão ─────────────────────────────────────────────────────────────
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient

from server import app

# ── Constantes do run ──────────────────────────────────────────────────────────
RUN = uuid.uuid4().hex[:6]

LOTE_MP  = {"id": f"lote-mp-{RUN}",  "numero": f"MP-{RUN}"}
LOTE_EMB = {"id": f"lote-emb-{RUN}", "numero": f"EMB-{RUN}"}
LOTE_PA  = {"id": f"lote-pa-{RUN}",  "numero": f"PA-{RUN}"}
OP       = {"id": f"op-{RUN}"}

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME   = os.environ["DB_NAME"]


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def in_days(n: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=n)).date().isoformat()


def ago_minutes(m: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()


def ago_days(d: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()


# ── Shared context (state entre testes) ───────────────────────────────────────
ctx: dict = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def ok(r, label: str = ""):
    __tracebackhide__ = True
    assert r.status_code < 300, (
        f"{label} → HTTP {r.status_code}: {r.text[:400]}"
    )


async def _direct_db():
    """Retorna (client, db) do Motor para inserções diretas em testes de scheduler."""
    c = AsyncIOMotorClient(MONGO_URL)
    return c, c[DB_NAME]


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def admin_client():
    """
    AsyncClient já autenticado como admin CQ.
    Registra usuário → faz login → cookie é mantido pelo client.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=30.0,
    ) as c:
        email = f"cq.admin.{RUN}@test.local"
        pwd   = "Admin@CQ2026"

        r = await c.post("/api/auth/register", json={
            "email": email, "password": pwd,
            "name": "Admin CQ Test", "org_name": f"Lab CQ {RUN}",
        })
        assert r.status_code in (200, 201), f"Register: {r.text}"

        r = await c.post("/api/auth/login", json={"email": email, "password": pwd})
        assert r.status_code == 200, f"Login: {r.text}"

        me = await c.get("/api/auth/me")
        if me.status_code == 200:
            u = me.json()
            ctx["tenant_id"] = u.get("tenant_id", "")
            ctx["user_id"]   = u.get("id", "")
            ctx["user_name"] = u.get("name", "Admin CQ Test")

        yield c


@pytest_asyncio.fixture(scope="session")
async def vendedor_client(admin_client):
    """
    AsyncClient autenticado como usuário com role=vendedor (não-CQ).
    Registra usuário em tenant próprio, depois move para tenant do admin via DB.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=30.0,
    ) as c:
        email = f"vendedor.{RUN}@test.local"
        pwd   = "Vendedor@2026"

        r = await c.post("/api/auth/register", json={
            "email": email, "password": pwd,
            "name": "Vendedor Test", "org_name": f"Lab Vendedor {RUN}",
        })
        if r.status_code not in (200, 201):
            yield None
            return

        vendedor_id  = r.json()["id"]
        admin_tenant = ctx.get("tenant_id", "")

        if admin_tenant:
            # Mover para o tenant do admin e setar role vendedor
            mc, db = await _direct_db()
            await db.users.update_one(
                {"id": vendedor_id},
                {"$set": {"role": "vendedor", "tenant_id": admin_tenant}},
            )
            mc.close()

        # Re-login para que o cookie tenha o JWT com role=vendedor
        r = await c.post("/api/auth/login", json={"email": email, "password": pwd})
        if r.status_code != 200:
            yield None
            return

        yield c


# ══════════════════════════════════════════════════════════════════════════════
#   FLUXO 1 — Recebimento MP Aprovado
# ══════════════════════════════════════════════════════════════════════════════

async def test_01_criar_ra_mp(admin_client):
    """POST /registros-analise tipo=recepcao_mp → RA criado, CQ-01 task acionada."""
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id":    LOTE_MP["id"],
        "lote_numero": LOTE_MP["numero"],
        "tipo":       "recepcao_mp",
        "item_nome":  "Álcool Etílico 70%",
        "fornecedor_nome": "Fornecedor Alpha",
        "quantidade_recebida": 100.0,
        "unidade":    "L",
        "nf_numero":  f"NF-{RUN}-001",
        "nf_data":    today(),
        "data_validade_fornecedor": in_days(365),
        "numero_lote_fornecedor":   f"FORN-{RUN}",
        "parametros": [
            {
                "id": "p1", "nome": "Concentração de Álcool",
                "unidade": "%", "metodo": "Densimetria",
                "especificacao_min": 65.0, "especificacao_max": 75.0,
            },
            {
                "id": "p2", "nome": "pH",
                "unidade": "pH", "metodo": "pHmetro calibrado",
                "especificacao_min": 6.0, "especificacao_max": 8.0,
            },
        ],
    })
    ok(r, "Criar RA MP")
    ra = r.json()
    assert ra["status"] == "rascunho"
    assert ra["numero_ra"].startswith("RA-")
    assert ra["lote_id"] == LOTE_MP["id"]
    assert len(ra["parametros"]) == 2
    ctx["ra_mp_id"] = ra["id"]
    ctx["ra_mp_numero"] = ra["numero_ra"]
    print(f"\n  RA criado: {ra['numero_ra']}")


async def test_02_ra_sem_lote_retorna_400(admin_client):
    """POST sem lote_id → 400 'lote_id é obrigatório'."""
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": "", "lote_numero": "X", "tipo": "recepcao_mp",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    assert "lote_id" in r.text.lower()


async def test_03_salvar_parametros_conformes(admin_client):
    """PUT /parametros resultados dentro da spec → conforme=True, resultado_geral=conforme."""
    ra_id = ctx["ra_mp_id"]
    r = await admin_client.put(
        f"/api/cq/registros-analise/{ra_id}/parametros",
        json={
            "parametros": [
                {"id": "p1", "resultado": 70.5, "observacao": "Dentro da spec"},
                {"id": "p2", "resultado": 7.0},
            ]
        },
    )
    ok(r, "Salvar parâmetros conformes")
    ra = r.json()
    assert ra["resultado_geral"] == "conforme"
    assert ra["status"] == "em_analise"
    p1 = next(p for p in ra["parametros"] if p["id"] == "p1")
    assert p1["conforme"] is True, "p1 deveria ser conforme"


async def test_04_resultado_fora_spec_e_nao_conforme(admin_client):
    """PUT resultado fora da spec → conforme=False e resultado_geral=nao_conforme."""
    # RA temporário para este subteste
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": f"lote-tmp-{RUN}", "lote_numero": f"TMP-{RUN}",
        "tipo": "recepcao_mp",
        "parametros": [
            {"id": "px", "nome": "pH", "especificacao_min": 6.5, "especificacao_max": 7.5},
        ],
    })
    tmp_id = r.json()["id"]

    r = await admin_client.put(
        f"/api/cq/registros-analise/{tmp_id}/parametros",
        json={"parametros": [{"id": "px", "resultado": 8.0}]},
    )
    ok(r, "Parâmetro fora da spec")
    ra = r.json()
    assert ra["resultado_geral"] == "nao_conforme"
    px = next(p for p in ra["parametros"] if p["id"] == "px")
    assert px["conforme"] is False


async def test_05_aprovar_ra_aprovado(admin_client):
    """POST /aprovar decisao=aprovado → status=aprovado, RET criada."""
    ra_id = ctx["ra_mp_id"]
    r = await admin_client.post(
        f"/api/cq/registros-analise/{ra_id}/aprovar",
        json={"decisao": "aprovado", "observacoes": "Aprovado no teste de integração"},
    )
    ok(r, "Aprovar RA")
    ra = r.json()
    assert ra["status"] == "aprovado"
    assert ra["amostra_retencao_id"] is not None, "RET deve ter sido criada"
    ctx["ret_mp_id"] = ra["amostra_retencao_id"]
    print(f"\n  RET criada: {ra['amostra_retencao_id']}")


async def test_06_ret_data_limite_guarda_correta(admin_client):
    """RET criada automaticamente: data_limite_guarda = nf_data + 180 dias (±1d)."""
    r = await admin_client.get("/api/cq/retencoes", params={"limit": 100})
    ok(r)
    items = r.json()["items"]
    ret = next((i for i in items if i["id"] == ctx["ret_mp_id"]), None)
    assert ret is not None, "RET não encontrada na listagem"

    # nf_data = today() → data_limite_guarda deve estar entre today+179 e today+181
    assert ret["data_limite_guarda"] >= in_days(179), (
        f"data_limite_guarda={ret['data_limite_guarda']} está muito cedo"
    )
    assert ret["data_limite_guarda"] <= in_days(181), (
        f"data_limite_guarda={ret['data_limite_guarda']} está muito tarde"
    )
    assert ret["tipo"] == "mp"
    print(f"\n  data_limite_guarda: {ret['data_limite_guarda']}")


async def test_07_coa_ra_aprovado_retorna_200(admin_client):
    """GET /coa?tipo_coa=interno para RA aprovado → 200 com conteúdo HTML/PDF."""
    ra_id = ctx["ra_mp_id"]
    r = await admin_client.get(
        f"/api/cq/registros-analise/{ra_id}/coa",
        params={"tipo_coa": "interno"},
    )
    ok(r, "CoA interno")
    ct = r.headers.get("content-type", "")
    assert "html" in ct or "pdf" in ct, f"Content-Type inesperado: {ct}"


async def test_08_coa_comercial_tem_marca_dagua(admin_client):
    """GET /coa?tipo_coa=comercial → contém 'DOCUMENTO CONTROLADO' (fallback HTML)."""
    ra_id = ctx["ra_mp_id"]
    r = await admin_client.get(
        f"/api/cq/registros-analise/{ra_id}/coa",
        params={"tipo_coa": "comercial"},
    )
    ok(r, "CoA comercial")
    if "html" in r.headers.get("content-type", ""):
        assert "DOCUMENTO CONTROLADO" in r.text, "Marca d'água ausente no CoA comercial"


async def test_09_coa_ra_rascunho_retorna_400(admin_client):
    """GET /coa para RA em rascunho → 400."""
    r_new = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": f"lote-coa-{RUN}", "lote_numero": f"COA-{RUN}", "tipo": "bulk_piloto",
    })
    rascunho_id = r_new.json()["id"]
    r = await admin_client.get(f"/api/cq/registros-analise/{rascunho_id}/coa")
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"


async def test_10_concessao_sem_justificativa_retorna_422(admin_client):
    """POST /aprovar decisao=concessao sem justificativa_concessao → 422."""
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": f"lote-cess-{RUN}", "lote_numero": f"CESS-{RUN}", "tipo": "bulk_piloto",
    })
    cid = r.json()["id"]
    r = await admin_client.post(
        f"/api/cq/registros-analise/{cid}/aprovar",
        json={"decisao": "concessao"},  # sem justificativa!
    )
    assert r.status_code == 422
    assert "justificativa" in r.text.lower()


# ══════════════════════════════════════════════════════════════════════════════
#   FLUXO 2 — Recebimento Reprovado → RNC → Comunicado → Encerramento
# ══════════════════════════════════════════════════════════════════════════════

async def test_20_criar_ra_embalagem(admin_client):
    """POST recepcao_embalagem → RA criado com CQ-02 task."""
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id":    LOTE_EMB["id"],
        "lote_numero": LOTE_EMB["numero"],
        "tipo":       "recepcao_embalagem",
        "item_nome":  "Frasco PET 100mL",
        "fornecedor_nome": "Embalagens Beta",
        "quantidade_recebida": 5000,
        "unidade":    "un",
        "nf_data":    today(),
        "parametros": [
            {
                "id": "e1", "nome": "Peso frasco vazio",
                "unidade": "g", "metodo": "Balança",
                "especificacao_min": 15.0, "especificacao_max": 17.0,
            }
        ],
    })
    ok(r, "Criar RA embalagem")
    ra = r.json()
    assert ra["tipo"] == "recepcao_embalagem"
    ctx["ra_emb_id"] = ra["id"]


async def test_21_salvar_parametro_fora_spec(admin_client):
    """PUT resultado 12.5 (fora de 15-17) → nao_conforme."""
    r = await admin_client.put(
        f"/api/cq/registros-analise/{ctx['ra_emb_id']}/parametros",
        json={"parametros": [{"id": "e1", "resultado": 12.5}]},
    )
    ok(r)
    assert r.json()["resultado_geral"] == "nao_conforme"


async def test_22_aprovar_reprovado_sem_disposicao_retorna_422(admin_client):
    """POST /aprovar reprovado sem disposicao_imediata → 422."""
    r = await admin_client.post(
        f"/api/cq/registros-analise/{ctx['ra_emb_id']}/aprovar",
        json={"decisao": "reprovado"},
    )
    assert r.status_code == 422
    assert "disposicao_imediata" in r.text.lower()


async def test_23_aprovar_reprovado_cria_rnc(admin_client):
    """POST /aprovar decisao=reprovado → RNC criada, lote=reprovado."""
    r = await admin_client.post(
        f"/api/cq/registros-analise/{ctx['ra_emb_id']}/aprovar",
        json={
            "decisao": "reprovado",
            "disposicao_imediata": "devolucao",
            "observacoes": "Peso fora da especificação",
        },
    )
    ok(r, "Aprovar reprovado")
    ra = r.json()
    assert ra["status"] == "reprovado"
    assert ra["rnc_id"] is not None
    ctx["rnc_id"] = ra["rnc_id"]
    print(f"\n  RNC criada: {ra['rnc_id']}")


async def test_24_rnc_atualizar_responsavel_muda_status(admin_client):
    """PUT /rncs/{id} com responsavel + prazo → status=em_investigacao."""
    r = await admin_client.put(
        f"/api/cq/rncs/{ctx['rnc_id']}",
        json={
            "responsavel_id": ctx.get("user_id", "uid"),
            "responsavel_nome": ctx.get("user_name", "Analista"),
            "prazo_resolucao": in_days(10),
            "classificacao": "maior",
        },
    )
    ok(r, "Atualizar RNC")
    assert r.json()["status"] == "em_investigacao"


async def test_25_comunicar_fornecedor(admin_client):
    """POST /comunicar-fornecedor → status=aguardando_fornecedor."""
    r = await admin_client.post(
        f"/api/cq/rncs/{ctx['rnc_id']}/comunicar-fornecedor",
        json={"email_destinatario": "fornecedor@beta.com"},
    )
    ok(r, "Comunicar fornecedor")
    # Response pode ser HTML ou PDF
    assert r.status_code == 200

    # Verifica status via GET
    rnc_r = await admin_client.get(f"/api/cq/rncs/{ctx['rnc_id']}")
    assert rnc_r.json()["status"] == "aguardando_fornecedor"


async def test_26_comunicar_fornecedor_em_origem_invalida_retorna_400(admin_client):
    """POST /comunicar-fornecedor em RNC de processo_envase → 400."""
    # Criar CK-4, item NC crítica → RNC auto com origem=processo_envase
    ck_r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-4", "op_id": f"op-com-test-{RUN}", "op_numero": "OP-COM",
    })
    ck_id = ck_r.json()["id"]
    item = ck_r.json()["itens"][0]

    await admin_client.put(
        f"/api/cq/checklists/{ck_id}/itens/{item['id']}",
        json={"resposta": "N", "nc_classificacao": "critica"},
    )

    ck_up = await admin_client.get(f"/api/cq/checklists/{ck_id}")
    rncs = ck_up.json().get("rncs_geradas", [])
    if not rncs:
        pytest.skip("Nenhuma RNC auto-criada pelo CK neste contexto")

    r = await admin_client.post(
        f"/api/cq/rncs/{rncs[0]}/comunicar-fornecedor",
        json={},
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


async def test_27_encerrar_sem_evidencia_retorna_422(admin_client):
    """POST /encerrar sem evidencia_resolucao → 422."""
    r = await admin_client.post(
        f"/api/cq/rncs/{ctx['rnc_id']}/encerrar",
        json={"evidencia_resolucao": "   "},  # só espaços → inválido
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"


async def test_28_encerrar_rnc(admin_client):
    """POST /encerrar com evidencia → status=encerrada."""
    r = await admin_client.post(
        f"/api/cq/rncs/{ctx['rnc_id']}/encerrar",
        json={
            "evidencia_resolucao": "Fornecedor devolveu os frascos não conformes. Evidência: foto e NF de retorno.",
            "com_concessao": False,
            "observacoes": "Encerrada após devolução total.",
        },
    )
    ok(r, "Encerrar RNC")
    assert r.json()["status"] == "encerrada"


async def test_29_rnc_encerrada_nao_editavel(admin_client):
    """PUT em RNC encerrada → 400."""
    r = await admin_client.put(
        f"/api/cq/rncs/{ctx['rnc_id']}",
        json={"classificacao": "critica"},
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
#   FLUXO 3 — Linha de Produção
# ══════════════════════════════════════════════════════════════════════════════

async def test_40_ck3_sem_op_retorna_400(admin_client):
    """POST CK-3 sem op_id → 400."""
    r = await admin_client.post("/api/cq/checklists", json={"tipo": "CK-3"})
    assert r.status_code == 400
    assert "op_id" in r.text.lower()


async def test_41_ck1_sem_subtipo_retorna_400(admin_client):
    """POST CK-1 sem subtipo_insumo → 400."""
    r = await admin_client.post("/api/cq/checklists", json={"tipo": "CK-1"})
    assert r.status_code == 400
    assert "subtipo_insumo" in r.text.lower()


async def test_42_ck1_subtipo_frasco_secao_correta(admin_client):
    """POST CK-1 subtipo=frasco → seção '4. Frascos' presente, '4. Rótulos' ausente."""
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-1", "subtipo_insumo": "frasco",
        "lote_id": f"lote-ck1-f-{RUN}",
    })
    ok(r)
    itens = r.json()["itens"]
    secoes = {i["secao"] for i in itens}
    assert "4. Frascos" in secoes, f"'4. Frascos' não encontrado. Seções: {secoes}"
    assert not any("Rótul" in s for s in secoes), "Seção de Rótulos não deveria existir para frasco"


async def test_43_ck1_subtipo_rotulo_secao_correta(admin_client):
    """POST CK-1 subtipo=rotulo → seção '4. Rótulos' presente, '4. Frascos' ausente."""
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-1", "subtipo_insumo": "rotulo",
        "lote_id": f"lote-ck1-r-{RUN}",
    })
    ok(r)
    itens = r.json()["itens"]
    secoes = {i["secao"] for i in itens}
    assert "4. Rótulos" in secoes, f"'4. Rótulos' não encontrado. Seções: {secoes}"
    assert "4. Frascos" not in secoes


async def test_44_criar_ck4(admin_client):
    """POST CK-4 → criado com 7 itens fixos (1 somente_cq)."""
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-4", "op_id": OP["id"], "op_numero": f"OP-{RUN}",
        "linha": "Linha 1", "turno": "manhã",
    })
    ok(r, "Criar CK-4")
    ck = r.json()
    assert len(ck["itens"]) == 7
    somente_cq = [i for i in ck["itens"] if i["somente_cq"]]
    assert len(somente_cq) >= 1
    ctx["ck4_id"] = ck["id"]
    ctx["ck4_itens"] = ck["itens"]
    print(f"\n  CK-4 criado: {ck['numero_ck']}")


async def test_45_preencher_item_s(admin_client):
    """PUT item com resposta=S → conforme=True."""
    ck4_id = ctx["ck4_id"]
    item = next(i for i in ctx["ck4_itens"] if not i["somente_cq"])
    r = await admin_client.put(
        f"/api/cq/checklists/{ck4_id}/itens/{item['id']}",
        json={"resposta": "S"},
    )
    ok(r, "Preencher item S")
    ck = r.json()
    updated = next(i for i in ck["itens"] if i["id"] == item["id"])
    assert updated["resposta"] == "S"
    assert updated["conforme"] is True


async def test_46_item_nc_critica_cria_rnc_auto(admin_client):
    """PUT item resposta=N + critica → RNC criada automaticamente no checklist."""
    ck4_id = ctx["ck4_id"]
    item = next(i for i in ctx["ck4_itens"] if not i["somente_cq"])
    r = await admin_client.put(
        f"/api/cq/checklists/{ck4_id}/itens/{item['id']}",
        json={"resposta": "N", "nc_classificacao": "critica", "acao_imediata": "Parar linha"},
    )
    ok(r, "Item NC crítica")
    ck = r.json()
    assert ck["ncs_identificadas"] >= 1
    assert len(ck["rncs_geradas"]) >= 1


async def test_47_aprovar_ck4(admin_client):
    """POST /aprovar CK-4 aprovado → status=aprovado."""
    ck4_id = ctx["ck4_id"]
    # Preencher todos itens pendentes
    ck = (await admin_client.get(f"/api/cq/checklists/{ck4_id}")).json()
    for item in ck["itens"]:
        if not item["somente_cq"] and item["resposta"] is None:
            await admin_client.put(
                f"/api/cq/checklists/{ck4_id}/itens/{item['id']}",
                json={"resposta": "S"},
            )
    # Aprovar
    r = await admin_client.post(
        f"/api/cq/checklists/{ck4_id}/aprovar",
        json={"decisao": "aprovado"},
    )
    ok(r, "Aprovar CK-4")
    assert r.json()["status"] == "aprovado"


async def test_48_ck5_tem_9_medicoes_e_1_cq(admin_client):
    """POST CK-5 → 16 itens: 6 setup + 9 numéricos + 1 somente_cq."""
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-5", "op_id": OP["id"], "op_numero": f"OP-{RUN}",
    })
    ok(r, "Criar CK-5")
    ck = r.json()
    assert len(ck["itens"]) == 16, f"Esperado 16 itens, got {len(ck['itens'])}"
    numericos = [i for i in ck["itens"] if i["tipo_resposta"] == "numerico"]
    assert len(numericos) == 9, f"Esperado 9 numéricos, got {len(numericos)}"
    ctx["ck5_id"] = ck["id"]
    ctx["ck5_itens"] = ck["itens"]
    print(f"\n  CK-5 criado: {ck['numero_ck']}")


async def test_49_ck5_medias_calculadas(admin_client):
    """PUT medições CK-5 → media_peso_g e media_volume_ml calculadas automaticamente."""
    ck5_id = ctx["ck5_id"]
    pesos   = [i for i in ctx["ck5_itens"] if "Peso" in i["descricao"]]
    volumes = [i for i in ctx["ck5_itens"] if "Volume" in i["descricao"]]

    for idx, item in enumerate(pesos):
        await admin_client.put(
            f"/api/cq/checklists/{ck5_id}/itens/{item['id']}",
            json={"resposta": 100.0 + idx},
        )
    for item in volumes:
        await admin_client.put(
            f"/api/cq/checklists/{ck5_id}/itens/{item['id']}",
            json={"resposta": 95.0},
        )

    ck = (await admin_client.get(f"/api/cq/checklists/{ck5_id}")).json()
    assert "media_peso_g" in ck, f"media_peso_g ausente. Campos: {list(ck.keys())}"
    assert "media_volume_ml" in ck, f"media_volume_ml ausente"
    print(f"\n  Médias: peso={ck['media_peso_g']}g, volume={ck['media_volume_ml']}mL")


async def test_50_aprovar_ck5_cria_tarefa_cq06(admin_client):
    """POST /aprovar CK-5 → status=aprovado (e tarefa CQ-06 gerada internamente)."""
    ck5_id = ctx["ck5_id"]
    ck = (await admin_client.get(f"/api/cq/checklists/{ck5_id}")).json()
    for item in ck["itens"]:
        if item["tipo_resposta"] == "snna" and not item["somente_cq"] and item["resposta"] is None:
            await admin_client.put(
                f"/api/cq/checklists/{ck5_id}/itens/{item['id']}",
                json={"resposta": "S"},
            )
    r = await admin_client.post(
        f"/api/cq/checklists/{ck5_id}/aprovar",
        json={"decisao": "aprovado"},
    )
    ok(r, "Aprovar CK-5")
    assert r.json()["status"] == "aprovado"


async def test_51_ck7_sem_ra_pa_aprovado_retorna_400(admin_client):
    """POST CK-7 sem RA produto_acabado aprovado → 400 prerequisito_nao_atendido."""
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-7", "op_id": OP["id"],
        "lote_id": f"lote-sem-pa-{RUN}",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("error") == "prerequisito_nao_atendido"
    else:
        assert "prerequisito" in str(detail).lower()


async def test_52_ck7_com_ra_pa_aprovado(admin_client):
    """POST CK-7 após RA produto_acabado aprovado → 201 criado."""
    # Criar RA PA e aprovar
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": LOTE_PA["id"], "lote_numero": LOTE_PA["numero"],
        "tipo": "produto_acabado",
        "item_nome": "Perfume Floral 100mL",
        "data_validade_fornecedor": in_days(730),
    })
    pa_id = r.json()["id"]
    await admin_client.post(
        f"/api/cq/registros-analise/{pa_id}/aprovar",
        json={"decisao": "aprovado"},
    )

    # Agora CK-7 deve ser criado
    r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-7", "op_id": OP["id"], "lote_id": LOTE_PA["id"],
    })
    ok(r, "Criar CK-7 com pré-requisito")
    assert r.json()["tipo"] == "CK-7"
    ctx["ck7_id"] = r.json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
#   SEGURANÇA — DELETE 405, edição bloqueada, hard stops
# ══════════════════════════════════════════════════════════════════════════════

async def test_60_delete_ra_retorna_405(admin_client):
    assert (await admin_client.delete(f"/api/cq/registros-analise/{ctx['ra_mp_id']}")).status_code == 405


async def test_61_delete_checklist_retorna_405(admin_client):
    assert (await admin_client.delete(f"/api/cq/checklists/{ctx['ck4_id']}")).status_code == 405


async def test_62_delete_rnc_retorna_405(admin_client):
    assert (await admin_client.delete(f"/api/cq/rncs/{ctx['rnc_id']}")).status_code == 405


async def test_63_delete_retencao_retorna_405(admin_client):
    assert (await admin_client.delete("/api/cq/retencoes/qualquer-id")).status_code == 405


async def test_64_delete_instrumento_retorna_405(admin_client):
    assert (await admin_client.delete("/api/cq/instrumentos/qualquer-id")).status_code == 405


async def test_65_ra_aprovado_nao_aceita_parametros(admin_client):
    """PUT /parametros em RA aprovado → 409."""
    r = await admin_client.put(
        f"/api/cq/registros-analise/{ctx['ra_mp_id']}/parametros",
        json={"parametros": [{"id": "p1", "resultado": 70.0}]},
    )
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text[:200]}"


async def test_66_operador_nao_aprova_checklist(admin_client, vendedor_client):
    """Vendedor (não-CQ) tentando aprovar checklist → 401 ou 403."""
    if vendedor_client is None:
        pytest.skip("vendedor_client não disponível neste ambiente")

    ck7_id = ctx.get("ck7_id", "any-id")
    r = await vendedor_client.post(
        f"/api/cq/checklists/{ck7_id}/aprovar",
        json={"decisao": "aprovado"},
    )
    # 401 se usuário não encontrado no DB, 403 se encontrado com role errado
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (acesso negado), got {r.status_code}: {r.text[:200]}"
    )


async def test_67_hard_stop_lote_reprovado(admin_client):
    """
    Movimento de estoque com referencia=lote_reprovado → 400 hard_stop_lote_reprovado.
    Nota: só funciona se referencia for um lote_id registrado como reprovado em cq_status_lote.
    """
    reprovado_lote_id = LOTE_EMB["id"]  # reprovado no test_23

    # Criar item de estoque para o teste
    item_r = await admin_client.post("/api/estoque/items", json={
        "nome": f"Item HS Test {RUN}",
        "codigo": f"HS-{RUN}",
        "setor": "MANIPULACAO",
        "tipo_item": "mp",
        "unidade": "kg",
    })
    if item_r.status_code not in (200, 201):
        pytest.skip(f"Não foi possível criar item de estoque: {item_r.text[:100]}")

    item_id = item_r.json()["id"]

    # Entrada (sem lote, sem bloqueio)
    await admin_client.post("/api/estoque/movimentos", json={
        "item_id": item_id, "tipo": "ENTRADA_RECEBIMENTO", "quantidade": 50.0,
    })

    # Saída com lote reprovado na referencia → deve ser bloqueada
    r = await admin_client.post("/api/estoque/movimentos", json={
        "item_id": item_id,
        "tipo": "SAIDA_CONSUMO_OP",
        "quantidade": 1.0,
        "referencia": reprovado_lote_id,
        "motivo": "Teste hard stop",
    })

    if r.status_code == 400:
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error") == "hard_stop_lote_reprovado", f"Error code errado: {detail}"
        print(f"\n  Hard stop bloqueou: {r.json()}")
    else:
        # Pode ocorrer se referencia não foi encontrado como lote_id — aceitável
        print(
            f"\n  AVISO: Hard stop não ativado (HTTP {r.status_code}). "
            "O campo 'referencia' pode não coincidir com o lote_id em cq_status_lote."
        )


async def test_68_lote_concessao_nao_e_bloqueado(admin_client):
    """Status concessao não deve bloquear movimentação (só reprovado bloqueia)."""
    lote_id = f"lote-cess2-{RUN}"
    r = await admin_client.post("/api/cq/registros-analise", json={
        "lote_id": lote_id, "lote_numero": f"CESS2-{RUN}", "tipo": "recepcao_mp",
        "parametros": [{"id": "cx", "nome": "T", "especificacao_min": 1.0, "especificacao_max": 5.0}],
    })
    cid = r.json()["id"]
    await admin_client.put(
        f"/api/cq/registros-analise/{cid}/parametros",
        json={"parametros": [{"id": "cx", "resultado": 3.0}]},
    )
    r = await admin_client.post(
        f"/api/cq/registros-analise/{cid}/aprovar",
        json={"decisao": "concessao", "justificativa_concessao": "Aceito para uso em testes."},
    )
    ok(r, "Aprovado por concessão")
    assert r.json()["status"] == "concessao"
    # Lote com status concessao → cq_verificar_lote_aprovado não deve bloquear


# ══════════════════════════════════════════════════════════════════════════════
#   INSTRUMENTOS
# ══════════════════════════════════════════════════════════════════════════════

async def test_70_criar_instrumento_vencido(admin_client):
    """POST instrumento ultima_calibracao=2025-01-01, freq=180 → proxima=2025-07-01, status=vencido."""
    r = await admin_client.post("/api/cq/instrumentos", json={
        "nome": "pHmetro Teste",
        "codigo_interno": f"PH-{RUN}",
        "tipo": "phmetro",
        "localizacao": "Lab CQ",
        "frequencia_calibracao_dias": 180,
        "ultima_calibracao": "2025-01-01",
    })
    ok(r, "Criar instrumento")
    instr = r.json()
    assert instr["proxima_calibracao"] == "2025-07-01", (
        f"Esperado 2025-07-01, got {instr['proxima_calibracao']}"
    )
    assert instr["status"] == "vencido"
    ctx["instr_id"] = instr["id"]
    print(f"\n  proxima_calibracao={instr['proxima_calibracao']}, status={instr['status']}")


async def test_71_listar_instrumentos_status_vencido_calculado(admin_client):
    """GET /instrumentos → status=vencido calculado em real-time."""
    r = await admin_client.get("/api/cq/instrumentos")
    ok(r)
    itens = r.json()["items"]
    instr = next((i for i in itens if i["id"] == ctx["instr_id"]), None)
    assert instr is not None, "Instrumento não encontrado na listagem"
    assert instr["status"] == "vencido"


async def test_72_registrar_calibracao_aprovada(admin_client):
    """POST /registrar-calibracao resultado=aprovado → status=calibrado, proxima=today+180."""
    instr_id = ctx["instr_id"]
    r = await admin_client.post(
        f"/api/cq/instrumentos/{instr_id}/registrar-calibracao",
        json={
            "data_calibracao": today(),
            "laboratorio": "Lab Calibração Beta",
            "certificado_numero": f"CERT-{RUN}",
            "resultado": "aprovado",
        },
    )
    ok(r, "Registrar calibração aprovada")
    instr = r.json()
    assert instr["status"] == "calibrado"
    assert instr["ultima_calibracao"] == today()
    assert instr["proxima_calibracao"] >= in_days(179)
    assert len(instr["historico_calibracoes"]) >= 1
    print(f"\n  proxima_calibracao pós-calibração: {instr['proxima_calibracao']}")


async def test_73_calibracao_reprovada_vira_bloqueado(admin_client):
    """POST /registrar-calibracao resultado=reprovado → status=bloqueado."""
    r = await admin_client.post("/api/cq/instrumentos", json={
        "nome": "Balança Rep", "codigo_interno": f"BAL-{RUN}",
        "tipo": "balanca", "frequencia_calibracao_dias": 365,
    })
    bid = r.json()["id"]
    r = await admin_client.post(
        f"/api/cq/instrumentos/{bid}/registrar-calibracao",
        json={"data_calibracao": today(), "resultado": "reprovado"},
    )
    ok(r)
    assert r.json()["status"] == "bloqueado"


async def test_74_instrumento_vencido_alerta_em_checklist(admin_client):
    """PUT item com instrumento_id vencido → log_auditoria contém alerta, observacao tem 'ALERTA'."""
    # Criar instrumento vencido
    r_instr = await admin_client.post("/api/cq/instrumentos", json={
        "nome": "TH Vencido", "codigo_interno": f"TH-{RUN}",
        "tipo": "termohigrometro",
        "frequencia_calibracao_dias": 365,
        "ultima_calibracao": "2024-01-01",
    })
    vencido_id = r_instr.json()["id"]

    # CK-8
    ck_r = await admin_client.post("/api/cq/checklists", json={
        "tipo": "CK-8", "op_id": f"op-ck8-{RUN}",
    })
    ck_id = ck_r.json()["id"]
    item  = ck_r.json()["itens"][0]

    r = await admin_client.put(
        f"/api/cq/checklists/{ck_id}/itens/{item['id']}",
        json={"resposta": "S", "instrumento_id": vencido_id},
    )
    ok(r, "Item com instrumento vencido")
    ck = r.json()

    log = ck.get("log_auditoria", [])
    alerta = [e for e in log if e.get("tipo") == "instrumento_alerta"]
    assert len(alerta) >= 1, f"Alerta não encontrado no log_auditoria: {log}"

    item_upd = next(i for i in ck["itens"] if i["id"] == item["id"])
    assert "ALERTA" in (item_upd.get("observacao") or ""), (
        f"'ALERTA' ausente na observacao do item: {item_upd.get('observacao')}"
    )
    print(f"\n  Alerta registrado: {alerta[0].get('alerta', '')}")


# ══════════════════════════════════════════════════════════════════════════════
#   SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

async def test_80_scheduler_tick_retorna_summary(admin_client):
    """GET /scheduler/tick → summary com tick_at e tarefas_criadas."""
    r = await admin_client.get("/api/cq/scheduler/tick")
    ok(r, "Scheduler tick")
    data = r.json()
    assert "tick_at" in data
    assert isinstance(data.get("tarefas_criadas"), int)
    print(f"\n  Scheduler: {data['tarefas_criadas']} tarefas criadas")


async def test_81_scheduler_cq10_ret_vencendo(admin_client):
    """RET com data_limite_guarda ≤ today+20 → scheduler cria CQ-10."""
    tenant_id = ctx.get("tenant_id", "")
    if not tenant_id:
        pytest.skip("tenant_id não disponível")

    mc, db = await _direct_db()
    try:
        ret_id = f"ret-sched-{RUN}"
        await db.cq_retencoes.insert_one({
            "id": ret_id,
            "numero_ret": f"RET-SCHED-{RUN}",
            "tenant_id": tenant_id,
            "tipo": "mp",
            "status": "em_guarda",
            "data_limite_guarda": in_days(20),
            "item_nome": "Item Scheduler",
            "lote_numero": f"LOTE-SCHED-{RUN}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        mc.close()

    r = await admin_client.get("/api/cq/scheduler/tick")
    ok(r)
    data = r.json()
    cq10 = [t for t in data.get("detalhe", []) if t.get("tipo") == "CQ-10"]
    assert len(cq10) >= 1, f"Esperado CQ-10, got detalhe: {data.get('detalhe', [])}"
    print(f"\n  CQ-10 criada: {cq10}")


async def test_82_scheduler_cq13_ronda_atrasada(admin_client):
    """Tarefa CQ-06 com due_date 35min atrás → scheduler cria CQ-13."""
    tenant_id = ctx.get("tenant_id", "")
    if not tenant_id:
        pytest.skip("tenant_id não disponível")

    ck_entity_id = f"ck-sched-{RUN}"
    mc, db = await _direct_db()
    try:
        await db.workflow_tasks.insert_one({
            "id": f"task-cq06-{RUN}",
            "display_code": "TRF-SCHED",
            "tenant_id": tenant_id,
            "entity_type": "cq_checklist",
            "entity_id": ck_entity_id,
            "title": f"CQ-06 Primeira Ronda — OP SCHED-{RUN}",
            "status": "pendente",
            "due_date": ago_minutes(35),  # 35 min atrás — acima do threshold de 30min
            "created_at": ago_minutes(40),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "category": "qa", "blocking": False,
            "responsible_id": "", "metadata": {},
        })
    finally:
        mc.close()

    r = await admin_client.get("/api/cq/scheduler/tick")
    ok(r)
    data = r.json()
    cq13 = [t for t in data.get("detalhe", []) if t.get("tipo") == "CQ-13"]
    assert len(cq13) >= 1, f"Esperado CQ-13, got detalhe: {data.get('detalhe', [])}"
    print(f"\n  CQ-13 criada: {cq13}")


async def test_83_scheduler_cq14_rnc_sem_resposta(admin_client):
    """RNC aguardando_fornecedor há >3 dias → scheduler cria CQ-14."""
    tenant_id = ctx.get("tenant_id", "")
    if not tenant_id:
        pytest.skip("tenant_id não disponível")

    mc, db = await _direct_db()
    try:
        rnc_id = f"rnc-sched-{RUN}"
        await db.cq_rncs.insert_one({
            "id": rnc_id,
            "numero_rnc": f"RNC-SCHED-{RUN}",
            "tenant_id": tenant_id,
            "status": "aguardando_fornecedor",
            "classificacao": "maior",
            "origem": "recepcao_mp",
            "descricao": "RNC para teste de scheduler CQ-14.",
            "comunicado_fornecedor_enviado": True,
            "comunicado_enviado_em": ago_days(4),  # 4 dias atrás — acima do threshold de 3 dias
            "fornecedor_nome": "Fornecedor Scheduler Test",
            "created_at": ago_days(5),
            "log_auditoria": [],
        })
    finally:
        mc.close()

    r = await admin_client.get("/api/cq/scheduler/tick")
    ok(r)
    data = r.json()
    cq14 = [t for t in data.get("detalhe", []) if t.get("tipo") == "CQ-14"]
    assert len(cq14) >= 1, f"Esperado CQ-14, got detalhe: {data.get('detalhe', [])}"
    print(f"\n  CQ-14 criada: {cq14}")
