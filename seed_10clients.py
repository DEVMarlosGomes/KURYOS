"""
KURYOS — Seed completo: 10 clientes em estágios diferentes com fluxo ponta-a-ponta.
Módulos: CRM (clients → projects → samples) → P&D → CQ → Compras
"""

import requests
import sys
from pymongo import MongoClient as _MC

BASE = "http://localhost:8000/api"
s = requests.Session()
s.headers["Content-Type"] = "application/json"


# ─── CNPJ GENERATOR ──────────────────────────────────────────────────────────
def gen_cnpj(n: int) -> str:
    """Gera um CNPJ válido a partir de um número base único."""
    base = f"{n:08d}0001"

    def digit(nums, weights):
        total = sum(int(d) * w for d, w in zip(nums, weights))
        r = total % 11
        return "0" if r < 2 else str(11 - r)

    d1 = digit(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digit(base + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    raw = base + d1 + d2
    return f"{raw[:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:14]}"


# ─── CLEANUP ─────────────────────────────────────────────────────────────────
SEED_CLIENT_NAMES = [
    "Bella Cosméticos", "NovaBeleza Ltda", "GreenCare Products", "AuraSkin",
    "MaxFresh", "EcoLab Beauty", "PureDerm", "VitaForm", "SunGlow Corp", "NaturaMix",
]

def cleanup_seeded_data():
    """Remove dados da seed anterior para re-popular limpo."""
    print("\n── Limpando dados da seed anterior ──")
    mdb = _MC("mongodb://127.0.0.1:27017")
    db2 = mdb["kuryos_crm"]

    # Clientes seeded
    clients = list(db2.crm_clients.find({"nome_empresa": {"$in": SEED_CLIENT_NAMES}}, {"id": 1, "nome_empresa": 1}))
    client_ids = [c["id"] for c in clients if "id" in c]
    if not client_ids:
        print("  Nenhum dado seed encontrado, prosseguindo.")
        mdb.close()
        return

    # Projetos desses clientes
    projects = list(db2.crm_projects.find({"cliente_id": {"$in": client_ids}}, {"id": 1}))
    proj_ids = [p["id"] for p in projects if "id" in p]

    # Amostras desses projetos
    if proj_ids:
        # pd_cards vinculados às amostras
        samples_to_del = list(db2.crm_samples.find({"projeto_id": {"$in": proj_ids}}, {"id": 1}))
        sample_ids_to_del = [s["id"] for s in samples_to_del if "id" in s]
        if sample_ids_to_del:
            db2.pd_cards.delete_many({"amostra_id": {"$in": sample_ids_to_del}})
        db2.crm_samples.delete_many({"projeto_id": {"$in": proj_ids}})

    # P&D requests desses projetos/clientes
    pd_requests = list(db2.pd_requests.find({"crm_project_id": {"$in": proj_ids}}, {"id": 1}))
    pd_ids_list = [p["id"] for p in pd_requests]
    # Também por client_name match (caso sem crm_project_id)
    for cname in SEED_CLIENT_NAMES:
        more = list(db2.pd_requests.find({"client_name": cname}, {"id": 1}))
        pd_ids_list += [p["id"] for p in more if "id" in p]
    pd_ids_list = list(set(pd_ids_list))

    if pd_ids_list:
        # Developments + formulas + tests
        devs = list(db2.pd_developments.find({"request_id": {"$in": pd_ids_list}}, {"id": 1}))
        dev_ids = [d["id"] for d in devs if "id" in d]
        if dev_ids:
            db2.pd_formula_items.delete_many({"formula_id": {"$in": [
                f["id"] for f in db2.pd_formulas.find({"development_id": {"$in": dev_ids}}, {"id": 1})
            ]}})
            db2.pd_formulas.delete_many({"development_id": {"$in": dev_ids}})
            db2.pd_tests.delete_many({"development_id": {"$in": dev_ids}})
            db2.pd_developments.delete_many({"id": {"$in": dev_ids}})
        db2.pd_requests.delete_many({"id": {"$in": pd_ids_list}})

    if proj_ids:
        db2.crm_projects.delete_many({"id": {"$in": proj_ids}})
    db2.crm_clients.delete_many({"id": {"$in": client_ids}})

    # TEST_PROJECT criado manualmente
    db2.crm_projects.delete_many({"nome_projeto": "TEST_PROJECT"})

    # Estoque e catálogo seeded
    stock_nomes = ["Carbomer 940", "Glicerina Vegetal USP", "Niacinamida 99%", "Acido Hialuronico",
                   "Phenoxyethanol", "Fragrance FRA-101", "Extrato de Camomila", "Agua Purificada RO"]
    db2.pd_stock.delete_many({"nome": {"$in": stock_nomes}})
    cat_nomes = ["Carbomer 940", "Glicerina Vegetal", "Niacinamida 99%", "Acido Hialuronico",
                 "Phenoxyethanol", "Fragrance Complex", "Extrato de Camomila", "Agua Purificada",
                 "BTMS-50", "Extrato de Argan"]
    db2.pd_catalog.delete_many({"nome": {"$in": cat_nomes}})

    print(f"  Removidos: {len(clients)} clientes, {len(proj_ids)} projetos, {len(pd_ids_list)} P&D requests")
    mdb.close()


# ─── HELPERS ─────────────────────────────────────────────────────────────────
ADMIN_USER_ID = None  # set after login


def login():
    global ADMIN_USER_ID
    r = s.post(f"{BASE}/auth/login", json={"email": "admin@kuryos.com", "password": "admin123"})
    assert r.status_code == 200, f"Login falhou: {r.text}"
    u = r.json()
    ADMIN_USER_ID = u["id"]
    print(f"[OK] Login: {u['name']} ({u['role']})")
    return u


def ok(label, r):
    if r.status_code in (200, 201):
        print(f"  [OK] {label}")
        return r.json()
    print(f"  [FAIL] {label}: {r.status_code} {r.text[:140]}")
    return None


# ─── CRM — CLIENTES ──────────────────────────────────────────────────────────
CLIENTS = [
    {"nome": "Bella Cosméticos",   "whatsapp": "11988001001", "email": "contato@bellacosmeticos.com.br",  "segmento": "marca_propria", "cats": ["skin_care_dermocosmeticos"]},
    {"nome": "NovaBeleza Ltda",    "whatsapp": "21991002002", "email": "comercial@novabeleza.com.br",      "segmento": "marca_propria", "cats": ["capilares"]},
    {"nome": "GreenCare Products", "whatsapp": "31977003003", "email": "pd@greencare.com.br",              "segmento": "marca_propria", "cats": ["corporal_spa"]},
    {"nome": "AuraSkin",           "whatsapp": "41966004004", "email": "projeto@auraskin.com.br",          "segmento": "marca_propria", "cats": ["skin_care_dermocosmeticos"]},
    {"nome": "MaxFresh",           "whatsapp": "51955005005", "email": "maxfresh@maxfresh.com.br",         "segmento": "industria",     "cats": ["higiene_pessoal"]},
    {"nome": "EcoLab Beauty",      "whatsapp": "61944006006", "email": "ceo@ecolabbeauty.com",             "segmento": "marca_propria", "cats": ["corporal_spa"]},
    {"nome": "PureDerm",           "whatsapp": "71933007007", "email": "vendas@purederm.com.br",           "segmento": "marca_propria", "cats": ["skin_care_dermocosmeticos"]},
    {"nome": "VitaForm",           "whatsapp": "81922008008", "email": "formulacao@vitaform.com.br",       "segmento": "marca_propria", "cats": ["capilares"]},
    {"nome": "SunGlow Corp",       "whatsapp": "91911009009", "email": "projetos@sunglow.com.br",          "segmento": "marca_propria", "cats": ["perfumaria"]},
    {"nome": "NaturaMix",          "whatsapp": "11900010010", "email": "natura@naturamix.com.br",          "segmento": "marca_propria", "cats": ["corporal_spa"]},
]


def create_clients():
    print("\n── Criando clientes CRM ──")
    ids = []
    for i, c in enumerate(CLIENTS):
        r = s.post(f"{BASE}/crm/clients", json={
            "nome_empresa": c["nome"],
            "cnpj": gen_cnpj(100 + i),
            "segmento": c["segmento"],
            "temperatura_lead": "quente" if i < 3 else ("morno" if i < 7 else "frio"),
            "responsavel_comercial": ADMIN_USER_ID,
            "contato_principal": {
                "nome": f"Comercial {c['nome'].split()[0]}",
                "whatsapp": c["whatsapp"],
                "email": c["email"],
            },
            "categoria_interesse": c["cats"],
            "canal_origem": "outro",
            "origem_lead": "outro",
        })
        result = ok(c["nome"], r)
        ids.append((c, result))
    return ids


# ─── CRM — PROJETOS (batch por cliente) ──────────────────────────────────────
PROJECTS = [
    {"nome": "Sérum Anti-Aging Premium",    "cat": "skincare"},
    {"nome": "Shampoo Hidratação Profunda",  "cat": "haircare"},
    {"nome": "Body Lotion Eco Formula",      "cat": "bodycare"},
    {"nome": "Creme Facial FPS 50+",         "cat": "skincare"},
    {"nome": "Gel Antisséptico Premium",     "cat": "higiene"},
    {"nome": "Óleo Corporal Relaxante",      "cat": "bodycare"},
    {"nome": "Máscara Capilar Reconstrução", "cat": "haircare"},
    {"nome": "Perfume Linha Verão",          "cat": "perfumaria"},
    {"nome": "Tônico Facial Vitamina C",     "cat": "skincare"},
    {"nome": "Sabonete Líquido Antibac",     "cat": "higiene"},
]


def create_projects(client_ids):
    print("\n── Criando projetos CRM ──")
    proj_ids = []
    for i, ((c, cdata), proj) in enumerate(zip(client_ids, PROJECTS)):
        if not cdata:
            proj_ids.append((c, proj, None))
            continue
        client_id = cdata.get("id")
        r = s.post(f"{BASE}/crm/projects/batch", json={
            "cliente_id": client_id,
            "projects": [{
                "nome_projeto": proj["nome"],
                "categoria": proj["cat"],
                "briefing_resumido": f"Desenvolvimento de {proj['nome']} para linha {proj['cat']}.",
                "tipo_servico": "desenvolvimento_formula",
                "sensorial_desejado": "Textura leve, não oleosa",
                "claims_desejados": "Hidratante, sem parabenos",
                "prazo_desejado_amostra": f"2026-{(i % 9)+1:02d}-30",
            }],
        })
        result = ok(proj["nome"], r)
        if isinstance(result, list):
            created = result[0] if result else None
        elif isinstance(result, dict):
            created = result.get("created", [None])[0]
        else:
            created = None
        proj_ids.append((c, proj, created))
    return proj_ids


# ─── CRM — AMOSTRAS (batch/v2 com variações — auto-cria pd_cards) ───────────
def create_samples(proj_ids):
    print("\n── Criando amostras CRM ──")
    sample_ids = []
    for i, (c, proj, pdata) in enumerate(proj_ids):
        if not pdata:
            sample_ids.append((c, proj, pdata, None))
            continue
        proj_id = pdata.get("id")
        r = s.post(f"{BASE}/crm/samples/batch/v2", json={
            "projeto_id": proj_id,
            "samples": [{
                "nome_produto": proj["nome"],
                "categoria": proj["cat"],
                "briefing_base": f"Desenvolvimento de {proj['nome']} para linha {proj['cat']}.",
                "produto": proj["nome"],
                "objetivo_projeto": f"Criar fórmula estável para {proj['nome']}",
                "aplicacao": proj["cat"],
                "textura_esperada": "Textura leve, absorção rápida",
                "sensorial": "Suave ao toque, perfume discreto",
                "ativos_claims": "Vitamina C, Ácido Hialurônico",
                "ph": "5.5 - 6.5",
                "orcamento_projeto": str(60000 + i * 10000),
                "variacoes": [],  # auto-cria variação A + pd_card
            }],
        })
        result = ok(f"Amostra: {proj['nome'][:35]}", r)
        if isinstance(result, list):
            created = result[0] if result else None
        elif isinstance(result, dict):
            created = result.get("created", [None])[0]
        else:
            created = None
        sample_ids.append((c, proj, pdata, created))
    return sample_ids


# ─── P&D — SOLICITAÇÕES ──────────────────────────────────────────────────────
def create_pd_requests(sample_ids):
    print("\n── Criando solicitações P&D ──")
    pd_ids = []
    types = ["Produto Novo", "Reformulação", "Extensão de Linha"]
    priorities = ["Normal", "Alta", "Urgente", "Baixa"]
    for i, (c, proj, pdata, sdata) in enumerate(sample_ids):
        payload = {
            "project_name": proj["nome"],
            "client_name": c["nome"],
            "request_type": types[i % 3],
            "category": proj["cat"],
            "description": f"Desenvolvimento de fórmula para {proj['nome']}. Cliente {c['nome']}.",
            "priority": priorities[i % 4],
            "deadline": f"2026-{(i % 9)+1:02d}-28",
            "objectives": f"Criar fórmula estável para {proj['nome']}",
            "references": "Referências de mercado apresentadas pelo cliente.",
            "packaging": "Frasco 50ml, tampa rosca",
        }
        if sdata:
            payload["crm_sample_id"] = sdata.get("id")
        if pdata:
            payload["crm_project_id"] = pdata.get("id")
        r = s.post(f"{BASE}/pd/requests", json=payload)
        result = ok(f"P&D: {proj['nome'][:35]}", r)
        pd_ids.append((c, proj, sdata, result))
    return pd_ids


# ─── P&D — FLUXO COMPLETO (ordem correta) ────────────────────────────────────
INGREDIENTS = [
    {"ingredient_name": "Agua Purificada",       "percentage": 88.7, "supplier": "Interno",  "price_per_kg": 0.50},
    {"ingredient_name": "Carbomer 940",          "percentage": 0.5,  "supplier": "Lubrizol", "price_per_kg": 45.00},
    {"ingredient_name": "Glicerina Vegetal USP", "percentage": 3.0,  "supplier": "Brenntag", "price_per_kg": 12.00},
    {"ingredient_name": "Niacinamida 99%",       "percentage": 5.0,  "supplier": "DSM",      "price_per_kg": 95.00},
    {"ingredient_name": "Acido Hialuronico",     "percentage": 0.2,  "supplier": "Givaudan", "price_per_kg": 1200.00},
    {"ingredient_name": "Extrato de Camomila",   "percentage": 1.5,  "supplier": "Beraca",   "price_per_kg": 85.00},
    {"ingredient_name": "Phenoxyethanol",        "percentage": 0.8,  "supplier": "Ashland",  "price_per_kg": 65.00},
    {"ingredient_name": "Fragrance Complex",     "percentage": 0.3,  "supplier": "IFF",      "price_per_kg": 380.00},
]

def advance_pd_statuses(pd_ids):
    """
    Fluxo correto:
      1. Avança para IN_PROGRESS (auto-cria development)
      2. Cria fórmula + ingredientes + testes
      3. Registra aprovação (para indices 6+)
      4. Avança para IN_TESTS → WAITING_APPROVAL → APPROVED → COMPLETED
    """
    print("\n── Avançando P&D com fórmulas e aprovações ──")

    # Índices e seus estágios finais desejados
    final_stages = {
        0: "OPEN",
        1: "IN_PROGRESS",
        2: "IN_PROGRESS",
        3: "IN_TESTS",
        4: "IN_TESTS",
        5: "WAITING_APPROVAL",
        6: "APPROVED",
        7: "APPROVED",
        8: "COMPLETED",
        9: "COMPLETED",
    }

    for i, (c, proj, sdata, req) in enumerate(pd_ids):
        if not req:
            continue
        req_id = req.get("id")
        target_final = final_stages.get(i, "OPEN")
        if target_final == "OPEN":
            continue  # index 0 fica em OPEN

        # PASSO 1: avançar para IN_PROGRESS
        r = s.put(f"{BASE}/pd/requests/{req_id}/status", json={"new_status": "IN_PROGRESS", "comment": "Iniciando desenvolvimento"})
        if r.status_code != 200:
            print(f"  [SKIP] P&D {i+1}: IN_PROGRESS falhou: {r.text[:80]}")
            continue
        print(f"  [OK] P&D {i+1} ({proj['nome'][:25]}): → IN_PROGRESS")

        # PASSO 2: buscar development (auto-criado pela transição)
        full = s.get(f"{BASE}/pd/requests/{req_id}/full")
        dev = full.json().get("development") if full.status_code == 200 else None
        dev_id = dev.get("id") if dev else None
        if not dev_id:
            print(f"  [FAIL] P&D {i+1}: sem development após IN_PROGRESS")
            continue

        # PASSO 3: criar fórmula + ingredientes
        rf = s.post(f"{BASE}/pd/developments/{dev_id}/formulas", json={
            "name": f"Formula {proj['nome'][:20]} v1.0",
            "version": 1, "volume": 1000, "volume_unit": "mL",
            "indice_perdas": 5.0, "notes": "Formula base inicial", "development_id": dev_id,
        })
        if rf.status_code in (200, 201):
            fid = rf.json().get("id")
            for ing in INGREDIENTS:
                s.post(f"{BASE}/pd/formulas/{fid}/items", json={**ing, "formula_id": fid})
            print(f"  [OK] P&D {i+1}: formula + {len(INGREDIENTS)} ingredientes")
        else:
            print(f"  [FAIL] P&D {i+1}: formula: {rf.text[:80]}")
            continue

        if target_final == "IN_PROGRESS":
            continue

        # PASSO 4: criar testes
        test_count = min(max(i - 2, 1), 3)
        for tt in ["pH", "Viscosidade", "Estabilidade"][:test_count]:
            s.post(f"{BASE}/pd/developments/{dev_id}/tests", json={
                "test_type": tt, "status": "APPROVED",
                "notes": f"Teste de {tt} realizado.", "result": "Conforme", "development_id": dev_id,
            })
        print(f"  [OK] P&D {i+1}: {test_count} testes")

        # PASSO 5: avançar para IN_TESTS
        r2 = s.put(f"{BASE}/pd/requests/{req_id}/status", json={"new_status": "IN_TESTS", "comment": "Fórmula registrada"})
        if r2.status_code != 200:
            print(f"  [SKIP] P&D {i+1}: IN_TESTS: {r2.text[:80]}")
            continue
        print(f"  [OK] P&D {i+1}: → IN_TESTS")

        if target_final == "IN_TESTS":
            continue

        # PASSO 6: avançar para WAITING_APPROVAL
        r3 = s.put(f"{BASE}/pd/requests/{req_id}/status", json={"new_status": "WAITING_APPROVAL", "comment": "Enviando ao comercial"})
        if r3.status_code != 200:
            print(f"  [SKIP] P&D {i+1}: WAITING_APPROVAL: {r3.text[:80]}")
            continue
        print(f"  [OK] P&D {i+1}: → WAITING_APPROVAL")

        if target_final == "WAITING_APPROVAL":
            continue

        # PASSO 7: registrar aprovação (necessária para APPROVED)
        s.post(f"{BASE}/pd/developments/{dev_id}/approval", json={
            "approved_by_client": True,
            "approved_by_internal": True,
            "notes": "Aprovado pelo cliente e internamente.",
        })
        print(f"  [OK] P&D {i+1}: aprovacao registrada")

        # PASSO 8: avançar para APPROVED
        r4 = s.put(f"{BASE}/pd/requests/{req_id}/status", json={"new_status": "APPROVED", "comment": "Amostra aprovada"})
        if r4.status_code != 200:
            print(f"  [SKIP] P&D {i+1}: APPROVED: {r4.text[:80]}")
            continue
        print(f"  [OK] P&D {i+1}: → APPROVED")

        if target_final == "APPROVED":
            continue

        # PASSO 9: avançar para COMPLETED
        r5 = s.put(f"{BASE}/pd/requests/{req_id}/status", json={"new_status": "COMPLETED", "comment": "Concluido"})
        if r5.status_code == 200:
            print(f"  [OK] P&D {i+1}: → COMPLETED")
        else:
            print(f"  [SKIP] P&D {i+1}: COMPLETED: {r5.text[:80]}")


# ─── CQ — REGISTROS DE ANÁLISE ────────────────────────────────────────────────
def create_registros_analise():
    print("\n── Criando Registros de Análise (CQ) ──")
    lotes = [
        {"num": "L2026001", "tipo": "recepcao_mp",        "item": "Carbomer 940",          "forn": "Lubrizol Brasil Ltda",    "nf": "NF-45231", "status": "aprovado"},
        {"num": "L2026002", "tipo": "recepcao_mp",        "item": "Glicerina Vegetal USP",  "forn": "Brenntag Brasil",         "nf": "NF-45232", "status": "aprovado"},
        {"num": "L2026003", "tipo": "recepcao_embalagem", "item": "Frasco 50ml PET Âmbar",  "forn": "Plasticon Embalagens",    "nf": "NF-45233", "status": "reprovado"},
        {"num": "L2026004", "tipo": "recepcao_mp",        "item": "Ácido Hialurônico",      "forn": "Givaudan Brasil",         "nf": "NF-45234", "status": "aprovado"},
        {"num": "L2026005", "tipo": "produto_acabado",    "item": "Sérum Anti-Aging V1",    "forn": None,                      "nf": None,       "status": "concessao"},
        {"num": "L2026006", "tipo": "recepcao_mp",        "item": "Phenoxyethanol",          "forn": "Ashland Chemical",        "nf": "NF-45235", "status": "aprovado"},
        {"num": "L2026007", "tipo": "recepcao_embalagem", "item": "Tampa Disc-Top 24/410",  "forn": "Plasticon Embalagens",    "nf": "NF-45236", "status": "aprovado"},
        {"num": "L2026008", "tipo": "bulk_piloto",        "item": "Shampoo Hidratação v2",  "forn": None,                      "nf": None,       "status": "aprovado"},
    ]
    for lot in lotes:
        payload = {
            "lote_id": f"LOTE-2026-{lot['num'][-3:]}",
            "lote_numero": lot["num"],
            "tipo": lot["tipo"],
            "item_nome": lot["item"],
            "parametros": [
                {"id": f"p1-{lot['num']}", "nome": "Aspecto Visual",            "resultado": "Conforme", "especificacao_min": None, "especificacao_max": None, "metodo": "Visual"},
                {"id": f"p2-{lot['num']}", "nome": "pH",                         "resultado": 6.0,       "especificacao_min": 5.0,  "especificacao_max": 7.0,  "metodo": "pHmetro"},
                {"id": f"p3-{lot['num']}", "nome": "Viscosidade (cP)",           "resultado": 15000,     "especificacao_min": 10000,"especificacao_max": 25000,"metodo": "Brookfield"},
                {"id": f"p4-{lot['num']}", "nome": "Contagem Microbiana (UFC/g)","resultado": 50,        "especificacao_min": None, "especificacao_max": 1000, "metodo": "USP 61"},
            ],
        }
        if lot.get("forn"):
            payload["fornecedor_nome"] = lot["forn"]
        if lot.get("nf"):
            payload["nf_numero"] = lot["nf"]
            payload["nf_data"] = "2026-05-20"
            payload["quantidade_recebida"] = 500
            payload["unidade"] = "kg"

        r = s.post(f"{BASE}/cq/registros-analise", json=payload)
        result = ok(f"RA: {lot['item'][:35]}", r)
        if not result:
            continue
        ra_id = result.get("id")

        # Preencher parâmetros
        params_update = [{"id": p["id"], "resultado": p["resultado"], "observacao": "Dentro da especificação"} for p in payload["parametros"]]
        s.put(f"{BASE}/cq/registros-analise/{ra_id}/parametros", json={"parametros": params_update})

        # Aprovar/reprovar
        aprov = {"decisao": lot["status"], "observacoes": f"Laudo {lot['num']} — {lot['status']}."}
        if lot["status"] == "reprovado":
            aprov["disposicao_imediata"] = "devolucao"
        if lot["status"] == "concessao":
            aprov["justificativa_concessao"] = "Aprovado por concessão — desvio leve de viscosidade com monitoramento adicional."
        ra_res = s.post(f"{BASE}/cq/registros-analise/{ra_id}/aprovar", json=aprov)
        if ra_res.status_code == 200:
            print(f"    → {lot['num']} {lot['status']}")


# ─── CQ — CHECKLISTS ──────────────────────────────────────────────────────────
def create_checklists():
    print("\n── Criando Checklists CQ ──")
    specs = [
        {"tipo": "CK-1", "nome": "Recebimento MP — Carbomer Lote L2026001",        "lote_id": "LOTE-2026-001", "subtipo_insumo": "frasco",  "turno": "Manha",  "linha": "Recebimento"},
        {"tipo": "CK-1", "nome": "Recebimento Embalagem — Frascos PET L2026003",    "lote_id": "LOTE-2026-003", "subtipo_insumo": "frasco",  "turno": "Tarde",  "linha": "Recebimento"},
        {"tipo": "CK-2", "nome": "Inspeção MP — Glicerina Lote L2026002",           "lote_id": "LOTE-2026-002",                               "turno": "Manha",  "linha": "Laboratorio"},
        {"tipo": "CK-3", "nome": "Assepsia Manipulação — OP-2026-041",              "op_id": "OP-2026-041", "op_numero": "OP-2026-041",       "turno": "Manha",  "linha": "Manipulacao 1"},
        {"tipo": "CK-4", "nome": "Assepsia Envase — OP-2026-042",                   "op_id": "OP-2026-042", "op_numero": "OP-2026-042",       "turno": "Manha",  "linha": "Envase 2"},
        {"tipo": "CK-5", "nome": "Setup Linha — OP-2026-043 Serum",                 "op_id": "OP-2026-043", "op_numero": "OP-2026-043",       "turno": "Manha",  "linha": "Linha 3"},
        {"tipo": "CK-6", "nome": "Ronda Processo — OP-2026-043 Turno Tarde",        "op_id": "OP-2026-043", "op_numero": "OP-2026-043",       "turno": "Tarde",  "linha": "Linha 3"},
        {"tipo": "CK-8", "nome": "Higiene Instalacoes — OP-2026-044",               "op_id": "OP-2026-044", "op_numero": "OP-2026-044",       "turno": "Manha",  "linha": "Fabrica Geral"},
    ]
    for spec in specs:
        payload = {"tipo": spec["tipo"], "nome": spec["nome"], "turno": spec.get("turno"), "linha": spec.get("linha")}
        if spec.get("lote_id"):
            payload["lote_id"] = spec["lote_id"]
        if spec.get("subtipo_insumo"):
            payload["subtipo_insumo"] = spec["subtipo_insumo"]
        if spec.get("op_id"):
            payload["op_id"] = spec["op_id"]
            payload["op_numero"] = spec.get("op_numero")
        r = s.post(f"{BASE}/cq/checklists", json=payload)
        result = ok(f"CK: {spec['nome'][:45]}", r)
        if not result:
            continue
        ck_id = result.get("id")
        for item in result.get("itens", []):
            item_id = item.get("id")
            if not item_id:
                continue
            resposta = "S" if item.get("tipo_resposta") == "snna" else "OK"
            s.put(f"{BASE}/cq/checklists/{ck_id}/itens/{item_id}", json={"resposta": resposta, "observacao": "Verificado e conforme."})
        if spec["tipo"] in ("CK-3", "CK-4", "CK-5", "CK-8"):
            res = s.post(f"{BASE}/cq/checklists/{ck_id}/aprovar", json={"decisao": "aprovado", "observacoes": "Aprovado pelo CQ."})
            if res.status_code == 200:
                print(f"    → {spec['tipo']} aprovado")


# ─── CQ — INSTRUMENTOS ───────────────────────────────────────────────────────
def create_instrumentos():
    print("\n── Criando Instrumentos CQ ──")
    instrumentos = [
        {"nome": "pHmetro Mettler Toledo",      "codigo": "INST-001", "tipo": "phmetro",        "loc": "Lab CQ",         "freq": 180},
        {"nome": "Balanca Analitica Shimadzu",   "codigo": "INST-002", "tipo": "balanca",         "loc": "Lab Formulacao", "freq": 365},
        {"nome": "Torquimetro Digital",          "codigo": "INST-003", "tipo": "torquimetro",     "loc": "Lab CQ",         "freq": 365},
        {"nome": "Densimetro Anton Paar",        "codigo": "INST-004", "tipo": "densimetro",      "loc": "Lab CQ",         "freq": 365},
        {"nome": "Termohigrometro Estabilidade", "codigo": "INST-005", "tipo": "termohigrometro", "loc": "Camara Estab.",  "freq": 90},
    ]
    for inst in instrumentos:
        r = s.post(f"{BASE}/cq/instrumentos", json={
            "nome": inst["nome"], "codigo_interno": inst["codigo"],
            "tipo": inst["tipo"], "localizacao": inst["loc"],
            "frequencia_calibracao_dias": inst["freq"],
            "ultima_calibracao": "2026-03-15",
        })
        if r.status_code == 409:
            print(f"  [SKIP] {inst['nome']} (já existe)")
            continue
        result = ok(inst["nome"], r)
        if result:
            s.post(f"{BASE}/cq/instrumentos/{result['id']}/registrar-calibracao", json={
                "data": "2026-03-15", "laboratorio": "LabCal Metrologia",
                "certificado_numero": f"CERT-{inst['codigo']}-2026",
                "resultado": "aprovado",
            })


# ─── P&D — ESTOQUE LAB ───────────────────────────────────────────────────────
def create_estoque():
    print("\n── Criando Estoque do Laboratório ──")
    items = [
        {"nome": "Carbomer 940",          "categoria": "mp",         "unidade_medida": "kg", "quantidade_atual": 15.5,  "quantidade_minima": 5.0,   "lote": "LB-2026-001", "loc": "Prateleira A1", "fornecedor": "Lubrizol"},
        {"nome": "Glicerina Vegetal USP", "categoria": "mp",         "unidade_medida": "kg", "quantidade_atual": 25.0,  "quantidade_minima": 10.0,  "lote": "LB-2026-002", "loc": "Prateleira A2", "fornecedor": "Brenntag"},
        {"nome": "Niacinamida 99%",       "categoria": "mp",         "unidade_medida": "kg", "quantidade_atual": 2.5,   "quantidade_minima": 1.0,   "lote": "LB-2026-003", "loc": "Geladeira G1",  "fornecedor": "DSM"},
        {"nome": "Acido Hialuronico",     "categoria": "mp",         "unidade_medida": "g",  "quantidade_atual": 500.0, "quantidade_minima": 100.0, "lote": "LB-2026-004", "loc": "Geladeira G1",  "fornecedor": "Givaudan"},
        {"nome": "Phenoxyethanol",        "categoria": "insumo",     "unidade_medida": "kg", "quantidade_atual": 5.0,   "quantidade_minima": 2.0,   "lote": "LB-2026-005", "loc": "Prateleira B3", "fornecedor": "Ashland"},
        {"nome": "Fragrance FRA-101",     "categoria": "insumo",     "unidade_medida": "kg", "quantidade_atual": 3.2,   "quantidade_minima": 1.0,   "lote": "LB-2026-006", "loc": "Sala Fragrancias","fornecedor": "IFF"},
        {"nome": "Extrato de Camomila",   "categoria": "mp",         "unidade_medida": "kg", "quantidade_atual": 1.8,   "quantidade_minima": 0.5,   "lote": "LB-2026-007", "loc": "Geladeira G2",  "fornecedor": "Beraca"},
        {"nome": "Agua Purificada RO",    "categoria": "mp",         "unidade_medida": "L",  "quantidade_atual": 200.0, "quantidade_minima": 50.0,  "lote": "LB-2026-008", "loc": "Cisterna Lab",  "fornecedor": "Interno"},
    ]
    for item in items:
        r = s.post(f"{BASE}/pd/stock", json={
            "nome": item["nome"],
            "categoria": item["categoria"],
            "unidade_medida": item["unidade_medida"],
            "quantidade_atual": item["quantidade_atual"],
            "quantidade_minima": item["quantidade_minima"],
            "lote": item["lote"],
            "validade": "2027-12-31",
            "localizacao": item["loc"],
            "custo_unitario": 50.0,
            "fornecedor": item["fornecedor"],
        })
        ok(item["nome"], r)


# ─── P&D — CATÁLOGO ───────────────────────────────────────────────────────────
def create_catalog():
    print("\n── Criando Catálogo de Matérias-Primas ──")
    catalog = [
        {"nome": "Carbomer 940",        "categoria": "polimero",     "unidade": "kg", "preco": 45.00,   "forn": "Lubrizol"},
        {"nome": "Glicerina Vegetal",   "categoria": "umectante",    "unidade": "kg", "preco": 12.00,   "forn": "Brenntag"},
        {"nome": "Niacinamida 99%",     "categoria": "ativo",        "unidade": "kg", "preco": 95.00,   "forn": "DSM"},
        {"nome": "Acido Hialuronico",   "categoria": "ativo",        "unidade": "kg", "preco": 1200.00, "forn": "Givaudan"},
        {"nome": "Phenoxyethanol",      "categoria": "conservante",  "unidade": "kg", "preco": 65.00,   "forn": "Ashland"},
        {"nome": "Fragrance Complex",   "categoria": "fragrancia",   "unidade": "kg", "preco": 380.00,  "forn": "IFF"},
        {"nome": "Extrato de Camomila", "categoria": "extrato",      "unidade": "kg", "preco": 85.00,   "forn": "Beraca"},
        {"nome": "Agua Purificada",     "categoria": "solvente",     "unidade": "L",  "preco": 0.50,    "forn": "Interno"},
        {"nome": "BTMS-50",             "categoria": "emulsificante","unidade": "kg", "preco": 38.00,   "forn": "Solvay"},
        {"nome": "Extrato de Argan",    "categoria": "ativo",        "unidade": "kg", "preco": 450.00,  "forn": "Aldivia"},
    ]
    for item in catalog:
        r = s.post(f"{BASE}/pd/catalog", json={
            "nome": item["nome"],
            "categoria": item["categoria"],
            "unidade": item["unidade"],
            "preco_rs_kg": item["preco"],
            "fornecedor": item["forn"],
        })
        ok(item["nome"], r)


# ─── COMPRAS — FORNECEDORES ───────────────────────────────────────────────────
def create_fornecedores():
    print("\n── Criando Fornecedores (Compras) ──")
    fornecedores = [
        {"razao": "Lubrizol Brasil Ltda",  "cnpj": gen_cnpj(200), "cats": ["polimeros", "quimica"]},
        {"razao": "Brenntag Brasil S.A.",  "cnpj": gen_cnpj(201), "cats": ["distribuidora", "quimica"]},
        {"razao": "IFF do Brasil Ltda",    "cnpj": gen_cnpj(202), "cats": ["fragrancias", "cosmeticos"]},
        {"razao": "Plasticon Embalagens",  "cnpj": gen_cnpj(203), "cats": ["embalagens"]},
        {"razao": "Ashland Chemical",      "cnpj": gen_cnpj(204), "cats": ["quimica", "conservantes"]},
    ]
    for forn in fornecedores:
        r = s.post(f"{BASE}/compras/fornecedores", json={
            "razao_social": forn["razao"],
            "nome_fantasia": forn["razao"].split()[0],
            "cnpj": forn["cnpj"],
            "categorias": forn["cats"],
        })
        if r.status_code == 409:
            print(f"  [SKIP] {forn['razao']} (ja existe)")
            continue
        result = ok(forn["razao"], r)
        if result:
            fid = result.get("id")
            s.post(f"{BASE}/compras/fornecedores/{fid}/homologacao/iniciar", json={"responsavel": "Admin Kuryos"})
            res = s.post(f"{BASE}/compras/fornecedores/{fid}/homologacao/decidir", json={
                "decisao": "homologado",
                "justificativa": "Fornecedor aprovado após auditoria documental.",
                "validade_dias": 365,
            })
            if res.status_code == 200:
                print(f"    → {forn['razao'][:30]} homologado")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  KURYOS — SEED COMPLETO: 10 CLIENTES + FLUXO E2E")
    print("=" * 60)

    cleanup_seeded_data()
    login()

    # CRM
    client_ids  = create_clients()
    proj_ids    = create_projects(client_ids)
    sample_ids  = create_samples(proj_ids)

    # P&D — cria pedidos, depois avança (fórmulas são criadas dentro do avanço)
    pd_ids      = create_pd_requests(sample_ids)
    advance_pd_statuses(pd_ids)

    # CQ
    create_registros_analise()
    create_checklists()
    create_instrumentos()

    # Estoque, Catálogo, Compras
    create_estoque()
    create_catalog()
    create_fornecedores()

    print("\n" + "=" * 60)
    print("  SEED CONCLUIDO!")
    print("=" * 60)
    print("\n  Acesse: http://localhost:3000")
    print("  Login:  admin@kuryos.com / admin123\n")
    print("  Modulos populados:")
    print("  [OK] CRM — 10 clientes, projetos, amostras")
    print("  [OK] P&D — 10 solicitacoes em 7 estagios, com formulas e testes")
    print("  [OK] CQ  — 8 RAs, 8 checklists, 5 instrumentos")
    print("  [OK] Compras — 5 fornecedores homologados")
    print("  [OK] Estoque Lab — 8 materias-primas")
    print("  [OK] Catalogo — 10 itens com preco")


if __name__ == "__main__":
    main()
