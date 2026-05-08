#!/usr/bin/env python3
"""
Focused test for the key CRM delete/add endpoints
"""

import requests
import json

BASE_URL = "https://approval-pipeline-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kuryos.com"
ADMIN_PASSWORD = "admin123"

def test_key_endpoints():
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
    
    # Create client
    print("\n📋 Creating client...")
    client_data = {
        "nome_empresa": "Test Delete Company",
        "contato_principal": {
            "nome": "Test User",
            "whatsapp": "+5511999999999",
            "email": "test@delete.com"
        },
        "canal_origem": "prospeccao_ativa"
    }
    
    response = session.post(f"{BASE_URL}/crm/clients", json=client_data)
    if response.status_code not in [200, 201]:
        print(f"❌ Client creation failed: {response.status_code}")
        return
    
    client = response.json()
    print(f"✅ Client created: {client['id']}")
    
    # Move client to projeto_em_discussao
    print("\n🔄 Moving client to projeto_em_discussao...")
    response = session.put(f"{BASE_URL}/crm/clients/{client['id']}/move", json={
        "stage": "qualificado"
    })
    
    response = session.put(f"{BASE_URL}/crm/clients/{client['id']}/move", json={
        "stage": "projeto_em_discussao"
    })
    
    if response.status_code != 200:
        print(f"❌ Client move failed: {response.status_code}")
        return
    
    print("✅ Client moved to projeto_em_discussao")
    
    # Create project
    print("\n📋 Creating project...")
    project_data = {
        "cliente_id": client['id'],
        "projects": [
            {
                "nome_projeto": "Test Delete Project",
                "categoria": "perfume",
                "descricao": "Project for delete testing"
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/projects/batch", json=project_data)
    if response.status_code not in [200, 201]:
        print(f"❌ Project creation failed: {response.status_code}")
        print(response.text)
        return
    
    projects = response.json()
    project = projects.get('created', [])[0] if projects.get('created') else None
    if not project:
        print("❌ No project returned")
        return
    
    print(f"✅ Project created: {project['id']}")
    
    # Move project to amostras
    print("\n🔄 Moving project to amostras...")
    response = session.put(f"{BASE_URL}/crm/projects/{project['id']}/move", json={
        "stage": "amostras"
    })
    
    if response.status_code != 200:
        print(f"❌ Project move failed: {response.status_code}")
        return
    
    print("✅ Project moved to amostras")
    
    # Create sample with variations
    print("\n📋 Creating sample with variations...")
    sample_data = {
        "projeto_id": project['id'],
        "samples": [
            {
                "nome_produto": "Test Delete Sample",
                "categoria": "perfume",
                "briefing_base": "Sample for delete testing",
                "variacoes": [
                    {
                        "descricao_aplicacao": "Variation A",
                        "percentual_fragrancia": 5.0,
                        "referencia_fragrancia": "Ref A",
                        "custo_fragrancia": 10.0,
                        "observacoes_especificas": "First variation"
                    },
                    {
                        "descricao_aplicacao": "Variation B",
                        "percentual_fragrancia": 7.5,
                        "referencia_fragrancia": "Ref B", 
                        "custo_fragrancia": 15.0,
                        "observacoes_especificas": "Second variation"
                    }
                ]
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/samples/batch/v2", json=sample_data)
    if response.status_code not in [200, 201]:
        print(f"❌ Sample creation failed: {response.status_code}")
        print(response.text)
        return
    
    samples = response.json()
    sample = samples.get('created', [])[0] if samples.get('created') else None
    if not sample:
        print("❌ No sample returned")
        return
    
    print(f"✅ Sample created: {sample['id']} with {len(sample.get('variacoes', []))} variations")
    
    # Test 1: Add variations to existing sample
    print("\n🧪 TEST 1: Add variations to existing sample")
    add_data = {
        "variacoes": [
            {
                "descricao_aplicacao": "Variation C",
                "percentual_fragrancia": 3.0,
                "referencia_fragrancia": "Ref C",
                "custo_fragrancia": 8.0,
                "observacoes_especificas": "Third variation"
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes", json=add_data)
    if response.status_code in [200, 201]:
        result = response.json()
        print(f"✅ Added variations successfully")
        print(f"   New variations: {len(result.get('new_variacoes', []))}")
    else:
        print(f"❌ Add variations failed: {response.status_code}")
        print(response.text)
    
    # Get updated sample
    response = session.get(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 200:
        updated_sample = response.json()
        variations = updated_sample.get('variacoes', [])
        print(f"   Total variations now: {len(variations)}")
        print(f"   Variation codes: {[v.get('codigo') for v in variations]}")
    
    # Test 2: Delete one variation
    print("\n🧪 TEST 2: Delete single variation")
    if len(variations) > 1:
        variation_to_delete = variations[1]  # Delete the second one
        response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{variation_to_delete['id']}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Deleted variation: {result.get('deleted_variacao')}")
        else:
            print(f"❌ Delete variation failed: {response.status_code}")
            print(response.text)
    
    # Test 3: Try to delete last variation (should fail)
    print("\n🧪 TEST 3: Try to delete last variation (should fail)")
    response = session.get(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 200:
        current_sample = response.json()
        current_variations = current_sample.get('variacoes', [])
        
        if len(current_variations) == 1:
            last_variation = current_variations[0]
            response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{last_variation['id']}")
            if response.status_code == 400:
                print("✅ Correctly blocked deletion of last variation")
            else:
                print(f"❌ Should have blocked deletion, got: {response.status_code}")
        else:
            print(f"   Skipping - still have {len(current_variations)} variations")
    
    # Test 4: Delete entire sample
    print("\n🧪 TEST 4: Delete entire sample")
    response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Deleted sample: {result.get('deleted_sample')}")
        print(f"   PD cards deleted: {result.get('deleted_pd_cards')}")
    else:
        print(f"❌ Delete sample failed: {response.status_code}")
        print(response.text)
    
    # Test 5: Delete entire project
    print("\n🧪 TEST 5: Delete entire project")
    response = session.delete(f"{BASE_URL}/crm/projects/{project['id']}")
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Deleted project: {result.get('deleted_project')}")
        print(f"   Samples deleted: {result.get('deleted_samples')}")
        print(f"   PD cards deleted: {result.get('deleted_pd_cards')}")
    else:
        print(f"❌ Delete project failed: {response.status_code}")
        print(response.text)
    
    print("\n🏁 Focused testing complete!")

if __name__ == "__main__":
    test_key_endpoints()