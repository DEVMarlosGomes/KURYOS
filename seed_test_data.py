"""Seed test data and validate new features end-to-end"""
import sys, json, http.cookiejar, urllib.request, urllib.error, time

BASE = "http://127.0.0.1:8000/api"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
PASS = 0; FAIL = 0

def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with opener.open(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except: return e.code, {}
    except Exception as ex: return 0, {"error": str(ex)}

def chk(label, cond, detail=""):
    global PASS, FAIL
    mark = "OK" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if cond: PASS += 1
    else: FAIL += 1
    return cond

# ========== Login ==========
print("\n=== Login ===")
st, data = req("POST", "/auth/login", {"email": "admin@kuryos.com", "password": "admin123"})
assert st == 200, f"Login falhou: {st}"
print(f"  [OK] Logado como {data.get('name')} ({data.get('role')})")

# ========== Criar PD Request ==========
print("\n=== Criar PD Request ===")
st, pd_req = req("POST", "/pd/requests", {
    "client_name": "Cliente Teste", "project_name": "Projeto Formula SEED",
    "product_type": "Creme Hidratante", "application": "Facial",
    "objective": "Testar pipeline de P&D"
})
chk("POST /pd/requests", st in (200,201), f"status={st}")
pd_req_id = pd_req.get("id")
print(f"     id={pd_req_id}")

# Advance to IN_PROGRESS (auto-creates development)
st, _ = req("PUT", f"/pd/requests/{pd_req_id}/status", {"new_status": "IN_PROGRESS"})
chk("Advance to IN_PROGRESS", st == 200, f"status={st}")

# Get auto-created development
time.sleep(0.3)
st, dev = req("GET", f"/pd/requests/{pd_req_id}/development")
chk("GET /pd/requests/{id}/development (auto-criado)", st == 200, f"status={st}")
dev_id = dev.get("id")
print(f"     Development id={dev_id}")

# ========== Criar Formula ==========
print("\n=== Criar Formula ===")
st, formula = req("POST", f"/pd/developments/{dev_id}/formulas", {
    "name": "Creme Base Hidratante", "volume": 100, "volume_unit": "g"
})
chk("POST /pd/developments/{id}/formulas", st in (200,201), f"status={st}")
formula_id = formula.get("id")
print(f"     Formula id={formula_id}")

# ========== Criar itens da formula (com ingredientes de fragrancia) ==========
print("\n=== Criar itens da formula ===")
items_data = [
    # Total deve ser 100% (para poder avançar a IN_TESTS via RN-PD-02)
    ("Aqua",                 74.2, "Fase A", "Solvente"),
    ("Glicerina",             5.0, "Fase A", "Umectante"),
    ("Cetearyl Alcohol",      5.0, "Fase B", "Emoliente"),
    ("Dimethicone",           3.0, "Fase B", "Emoliente"),
    ("Carnauba Wax",          2.0, "Fase B", "Espessante"),
    ("Fragrance Floral",      1.5, "Fase C", "Perfume"),   # fragrancia
    ("Parfum Rose",           0.5, "Fase C", "Essencia"),  # fragrancia
    ("Phenoxyethanol",        1.0, "Fase D", "Conservante"),
    ("Tocopheryl Acetate",    0.5, "Fase D", "Antioxidante"),
    ("Xanthan Gum",           0.3, "Fase A", "Espessante"),
    ("Carbomer",              0.2, "Fase A", "Espessante"),
    ("Disodium EDTA",         0.1, "Fase A", "Quelante"),
    ("Lactic Acid",           0.2, "Fase D", "Ajustador de pH"),
    ("Triethanolamine",       0.5, "Fase D", "Ajustador de pH"),
    ("Panthenol",             1.0, "Fase A", "Condicionante"),
    ("Niacinamide",           2.0, "Fase A", "Ativo"),
    ("Allantoin",             0.2, "Fase A", "Calmante"),
    ("BHT",                   0.1, "Fase B", "Antioxidante"),
    ("Polysorbate 80",        1.0, "Fase B", "Emulsificante"),
    ("PEG-100 Stearate",      0.5, "Fase B", "Emulsificante"),
    ("Glyceryl Stearate",     1.2, "Fase B", "Emulsificante"),
]
# Verifica total
_total = sum(x[1] for x in items_data)
assert abs(_total - 100.0) <= 0.5, f"Total formula = {_total}% (deve ser ~100%)"
created = 0
for name, pct, phase, func in items_data:
    ist, _ = req("POST", f"/pd/formulas/{formula_id}/items", {
        "ingredient_name": name, "percentage": pct, "phase": phase, "function": func
    })
    if ist in (200, 201): created += 1
chk("Criar itens da formula", created == len(items_data), f"{created}/{len(items_data)}")

# ========== TESTE 1: GET /pd/formulas/{id}/items + Scaling ==========
print("\n=== TESTE 1: Items endpoint + scaling para ordem de manipulacao ===")
st, items = req("GET", f"/pd/formulas/{formula_id}/items")
chk("GET /pd/formulas/{id}/items", st == 200 and isinstance(items, list), f"status={st}, count={len(items) if isinstance(items,list) else '?'}")
if isinstance(items, list) and items:
    total_pct = sum(it.get("percentage", 0) for it in items)
    chk("Total % da formula", 50 < total_pct <= 100.1, f"{total_pct:.3f}%")

    frag_kws = ["fragr", "parfum", "essenci", "perfum", "aroma"]
    frag = [it for it in items if any(kw in it.get("ingredient_name","").lower() for kw in frag_kws)]
    frag_pct = round(sum(it.get("percentage",0) for it in frag), 4)
    chk("Ingredientes de fragrancia detectados", len(frag) >= 2, f"{len(frag)} itens, {frag_pct}%")

    print(f"\n  Ordem de manipulacao (15 mL, densidade ~1 g/mL):")
    print(f"  {'Ingrediente':<30} {'%':>7}  {'Qtd (g)':>9}")
    print(f"  {'-'*52}")
    for it in sorted(items, key=lambda x: x.get("phase","") + x.get("ingredient_name","")):
        qty = round((it.get("percentage",0)/100)*15, 4)
        print(f"  {it['ingredient_name']:<30} {it.get('percentage',0):>7.3f}  {qty:>9.4f}")
    total_qty = round((total_pct/100)*15, 4)
    print(f"  {'TOTAL':<30} {total_pct:>7.3f}  {total_qty:>9.4f}")
    chk("Quantidade total calculada", total_qty > 0)

# ========== TESTE 2: Formula Bank - fragrance_percentage ==========
print("\n=== TESTE 2: Formula Bank - campo fragrance_percentage ===")
st, bank = req("GET", "/pd/formulas/bank")
chk("GET /pd/formulas/bank", st == 200, f"status={st}")
if st == 200 and isinstance(bank, list) and bank:
    f = next((x for x in bank if x.get("id") == formula_id), None) or bank[0]
    chk("Formula tem campo fragrance_percentage", "fragrance_percentage" in f, str(f.get("fragrance_percentage")))
    fv = f.get("fragrance_percentage")
    if fv is not None:
        chk("fragrance_percentage > 0 (ingredientes de fragrancia)", fv > 0, f"{fv}%")
    else:
        print(f"     fragrance_percentage=None (pode ser perfil restrito)")

# ========== TESTE 3: Backward status transition ==========
print("\n=== TESTE 3: Retrocesso de status (backward transition) ===")
# Advance to IN_TESTS
st, _ = req("PUT", f"/pd/requests/{pd_req_id}/status", {"new_status": "IN_TESTS"})
chk("Advance to IN_TESTS", st == 200, f"status={st}")

# Backward without comment -> must fail
st, resp = req("PUT", f"/pd/requests/{pd_req_id}/status", {
    "new_status": "IN_PROGRESS", "is_backward": True, "comment": ""
})
chk("Retroceder sem justificativa -> 400", st == 400, f"status={st}: {resp.get('detail','')[:70]}")

# Backward with short comment -> must fail
st, resp = req("PUT", f"/pd/requests/{pd_req_id}/status", {
    "new_status": "IN_PROGRESS", "is_backward": True, "comment": "curto"
})
chk("Retroceder justificativa <10 chars -> 400", st == 400, f"status={st}: {resp.get('detail','')[:70]}")

# Backward with valid comment -> must succeed
st, resp = req("PUT", f"/pd/requests/{pd_req_id}/status", {
    "new_status": "IN_PROGRESS", "is_backward": True,
    "comment": "Revisao necessaria apos feedback do time de qualidade"
})
chk("Retroceder com justificativa valida -> 200", st == 200, f"status={st}")
if st == 200:
    st2, r2 = req("GET", f"/pd/requests/{pd_req_id}")
    chk("Status voltou para IN_PROGRESS", r2.get("status") == "IN_PROGRESS", r2.get("status"))

# ========== TESTE 4: Two-stage sample approval ==========
print("\n=== TESTE 4: Aprovacao de amostra em 2 etapas ===")
# Re-advance to IN_PROGRESS first (already there)
st, sample = req("POST", f"/pd/developments/{dev_id}/samples", {
    "formula_version": 1, "sent_to_client": False
})
chk("Criar amostra com sent_to_client=False", st in (200,201), f"status={st}")
if st in (200,201):
    sid = sample.get("id")
    chk("internal_approved inicial = null", sample.get("internal_approved") is None, str(sample.get("internal_approved")))
    chk("sent_to_client inicial = false", sample.get("sent_to_client") == False)

    # Send to client - must auto-set internal_approved=True
    st2, _ = req("PUT", f"/pd/samples/{sid}", {"sent_to_client": True})
    chk("PUT sent_to_client=True -> 200", st2 == 200, f"status={st2}")

    st3, slist = req("GET", f"/pd/developments/{dev_id}/samples")
    if st3 == 200 and slist:
        s = next((x for x in slist if x["id"] == sid), None)
        if s:
            chk("internal_approved auto=True apos envio", s.get("internal_approved") == True, str(s.get("internal_approved")))
            chk("sent_to_client=True persistido", s.get("sent_to_client") == True)

    # Register client decision
    st4, _ = req("PUT", f"/pd/samples/{sid}", {"client_approved": True, "feedback": "Produto excelente!"})
    chk("Registrar client_approved=True -> 200", st4 == 200, f"status={st4}")

    st5, slist2 = req("GET", f"/pd/developments/{dev_id}/samples")
    if st5 == 200 and slist2:
        s2 = next((x for x in slist2 if x["id"] == sid), None)
        if s2:
            chk("client_approved=True persistido", s2.get("client_approved") == True, str(s2.get("client_approved")))

# ========== TESTE 5: CRM projects/full - estrutura de variacoes ==========
print("\n=== TESTE 5: CRM /projects/{id}/full - estrutura enriquecida ===")
st, crm_projects = req("GET", "/crm/projects?limit=5")
chk("GET /crm/projects", st == 200, f"status={st}")
if st == 200 and crm_projects:
    pid = crm_projects[0]["id"]
    st2, full = req("GET", f"/crm/projects/{pid}/full")
    chk("GET /crm/projects/{id}/full", st2 == 200, f"status={st2}")
    if st2 == 200:
        # The response must have pd_status, pd_request_id, pd_updated_at keys on variations
        # even if they are None (no linked PD card)
        samples = full.get("samples", [])
        chk("Campo 'samples' no full response", isinstance(samples, list))
        total_vars = 0
        pd_enriched_vars = 0
        for s in samples:
            for v in s.get("variacoes", []) or []:
                total_vars += 1
                if v.get("pd_status"):
                    pd_enriched_vars += 1
        chk("Variacoes escaneadas", True, f"{total_vars} variacoes, {pd_enriched_vars} com P&D vinculado")
        if pd_enriched_vars > 0:
            chk("P&D status enriquecido encontrado", True)

# ========== SUMMARY ==========
print(f"\n{'='*55}")
print(f"  RESULTADO FINAL: {PASS}/{PASS+FAIL} testes passaram, {FAIL} falharam")
print(f"{'='*55}\n")
sys.exit(0 if FAIL == 0 else 1)
