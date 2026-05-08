#!/usr/bin/env python3
"""
Test SKU blocking functionality for CRM delete endpoints
"""

import requests
import json

BASE_URL = "https://approval-pipeline-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kuryos.com"
ADMIN_PASSWORD = "admin123"

def test_sku_blocking():
    session = requests.Session()
    
    # Authenticate
    print("🔐 Authenticating...")
    response = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        print(f"❌ Auth failed: {response.status_code}")
        return
    
    print("✅ Authenticated successfully")
    
    # Create full workflow to test SKU blocking
    print("\n📋 Setting up test data...")
    
    # Create client
    client_data = {
        "nome_empresa": "SKU Block Test Company",
        "contato_principal": {
            "nome": "SKU Test User",
            "whatsapp": "+5511888888888",
            "email": "sku@test.com"
        },
        "canal_origem": "prospeccao_ativa"
    }
    
    response = session.post(f"{BASE_URL}/crm/clients", json=client_data)
    client = response.json()
    print(f"✅ Client created: {client['id']}")
    
    # Move client through stages
    session.put(f"{BASE_URL}/crm/clients/{client['id']}/move", json={"stage": "qualificado"})
    session.put(f"{BASE_URL}/crm/clients/{client['id']}/move", json={"stage": "projeto_em_discussao"})
    
    # Create project
    project_data = {
        "cliente_id": client['id'],
        "projects": [
            {
                "nome_projeto": "SKU Block Test Project",
                "categoria": "perfume",
                "descricao": "Project for SKU blocking test"
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/projects/batch", json=project_data)
    projects = response.json()
    project = projects.get('created', [])[0]
    print(f"✅ Project created: {project['id']}")
    
    # Move project to amostras
    session.put(f"{BASE_URL}/crm/projects/{project['id']}/move", json={"stage": "amostras"})
    
    # Create sample with variations
    sample_data = {
        "projeto_id": project['id'],
        "samples": [
            {
                "nome_produto": "SKU Block Test Sample",
                "categoria": "perfume",
                "briefing_base": "Sample for SKU blocking test",
                "variacoes": [
                    {
                        "descricao_aplicacao": "SKU Test Variation A",
                        "percentual_fragrancia": 5.0,
                        "referencia_fragrancia": "SKU Ref A",
                        "custo_fragrancia": 10.0,
                        "observacoes_especificas": "First variation for SKU test"
                    },
                    {
                        "descricao_aplicacao": "SKU Test Variation B",
                        "percentual_fragrancia": 7.5,
                        "referencia_fragrancia": "SKU Ref B",
                        "custo_fragrancia": 15.0,
                        "observacoes_especificas": "Second variation for SKU test"
                    }
                ]
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/samples/batch/v2", json=sample_data)
    samples = response.json()
    sample = samples.get('created', [])[0]
    print(f"✅ Sample created: {sample['id']} with {len(sample.get('variacoes', []))} variations")
    
    # Get the first variation to approve
    variations = sample.get('variacoes', [])
    if not variations:
        print("❌ No variations found")
        return
    
    variation_to_approve = variations[0]
    print(f"✅ Will approve variation: {variation_to_approve['id']} ({variation_to_approve.get('codigo')})")
    
    # Move variation through stages to approved (to create SKU)
    print("\n🔄 Approving variation to create SKU...")
    stages = ["em_elaboracao", "enviada", "aprovada"]
    
    for stage in stages:
        print(f"   Moving to {stage}...")
        response = session.put(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{variation_to_approve['id']}/move", json={
            "status": stage
        })
        
        if response.status_code != 200:
            print(f"❌ Failed to move to {stage}: {response.status_code}")
            print(response.text)
            return
    
    print("✅ Variation approved - SKU should be created")
    
    # Verify SKU was created by checking the variation
    response = session.get(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 200:
        updated_sample = response.json()
        approved_variation = None
        for v in updated_sample.get('variacoes', []):
            if v['id'] == variation_to_approve['id']:
                approved_variation = v
                break
        
        if approved_variation and approved_variation.get('sku_id'):
            print(f"✅ SKU created: {approved_variation['sku_id']}")
        else:
            print("⚠️  SKU not found in variation - continuing with tests anyway")
    
    # Test 1: Try to delete variation with SKU (should fail)
    print("\n🧪 TEST 1: Try to delete variation with SKU (should fail)")
    response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{variation_to_approve['id']}")
    if response.status_code == 400:
        print("✅ Correctly blocked deletion of variation with SKU")
        print(f"   Response: {response.json().get('detail', 'No detail')}")
    else:
        print(f"❌ Should have blocked deletion, got: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    
    # Test 2: Try to delete sample with SKU (should fail)
    print("\n🧪 TEST 2: Try to delete sample with SKU (should fail)")
    response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 400:
        print("✅ Correctly blocked deletion of sample with SKU")
        print(f"   Response: {response.json().get('detail', 'No detail')}")
    else:
        print(f"❌ Should have blocked deletion, got: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    
    # Test 3: Try to delete project with SKU (should fail)
    print("\n🧪 TEST 3: Try to delete project with SKU (should fail)")
    response = session.delete(f"{BASE_URL}/crm/projects/{project['id']}")
    if response.status_code == 400:
        print("✅ Correctly blocked deletion of project with SKU")
        print(f"   Response: {response.json().get('detail', 'No detail')}")
    else:
        print(f"❌ Should have blocked deletion, got: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    
    # Test 4: Delete the other variation (should work)
    print("\n🧪 TEST 4: Delete variation without SKU (should work)")
    if len(variations) > 1:
        variation_without_sku = variations[1]
        response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{variation_without_sku['id']}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Successfully deleted variation without SKU: {result.get('deleted_variacao')}")
        else:
            print(f"❌ Failed to delete variation without SKU: {response.status_code}")
            print(response.text)
    
    # Test 5: Try to delete last variation with SKU (should fail for multiple reasons)
    print("\n🧪 TEST 5: Try to delete last variation with SKU (should fail)")
    response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{variation_to_approve['id']}")
    if response.status_code == 400:
        print("✅ Correctly blocked deletion (either SKU or last variation)")
        print(f"   Response: {response.json().get('detail', 'No detail')}")
    else:
        print(f"❌ Should have blocked deletion, got: {response.status_code}")
    
    print("\n🏁 SKU blocking tests complete!")

if __name__ == "__main__":
    test_sku_blocking()