#!/usr/bin/env python3
"""
Test last variation blocking functionality
"""

import requests
import json

BASE_URL = "https://approval-pipeline-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kuryos.com"
ADMIN_PASSWORD = "admin123"

def test_last_variation_blocking():
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
    
    # Create full workflow to test last variation blocking
    print("\n📋 Setting up test data...")
    
    # Create client
    client_data = {
        "nome_empresa": "Last Variation Test Company",
        "contato_principal": {
            "nome": "Last Var Test User",
            "whatsapp": "+5511777777777",
            "email": "lastvar@test.com"
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
                "nome_projeto": "Last Variation Test Project",
                "categoria": "perfume",
                "descricao": "Project for last variation blocking test"
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/projects/batch", json=project_data)
    projects = response.json()
    project = projects.get('created', [])[0]
    print(f"✅ Project created: {project['id']}")
    
    # Move project to amostras
    session.put(f"{BASE_URL}/crm/projects/{project['id']}/move", json={"stage": "amostras"})
    
    # Create sample with 3 variations
    sample_data = {
        "projeto_id": project['id'],
        "samples": [
            {
                "nome_produto": "Last Variation Test Sample",
                "categoria": "perfume",
                "briefing_base": "Sample for last variation blocking test",
                "variacoes": [
                    {
                        "descricao_aplicacao": "Last Var Test A",
                        "percentual_fragrancia": 5.0,
                        "referencia_fragrancia": "Last Ref A",
                        "custo_fragrancia": 10.0,
                        "observacoes_especificas": "First variation"
                    },
                    {
                        "descricao_aplicacao": "Last Var Test B",
                        "percentual_fragrancia": 7.5,
                        "referencia_fragrancia": "Last Ref B",
                        "custo_fragrancia": 15.0,
                        "observacoes_especificas": "Second variation"
                    },
                    {
                        "descricao_aplicacao": "Last Var Test C",
                        "percentual_fragrancia": 3.0,
                        "referencia_fragrancia": "Last Ref C",
                        "custo_fragrancia": 8.0,
                        "observacoes_especificas": "Third variation"
                    }
                ]
            }
        ]
    }
    
    response = session.post(f"{BASE_URL}/crm/samples/batch/v2", json=sample_data)
    samples = response.json()
    sample = samples.get('created', [])[0]
    variations = sample.get('variacoes', [])
    print(f"✅ Sample created: {sample['id']} with {len(variations)} variations")
    print(f"   Variation codes: {[v.get('codigo') for v in variations]}")
    
    # Test 1: Delete first variation (should work)
    print("\n🧪 TEST 1: Delete first variation (should work)")
    if len(variations) >= 3:
        first_variation = variations[0]
        response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{first_variation['id']}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Successfully deleted first variation: {result.get('deleted_variacao')}")
        else:
            print(f"❌ Failed to delete first variation: {response.status_code}")
            print(response.text)
    
    # Test 2: Delete second variation (should work, leaving 1)
    print("\n🧪 TEST 2: Delete second variation (should work)")
    if len(variations) >= 3:
        second_variation = variations[1]
        response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{second_variation['id']}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Successfully deleted second variation: {result.get('deleted_variacao')}")
        else:
            print(f"❌ Failed to delete second variation: {response.status_code}")
            print(response.text)
    
    # Test 3: Try to delete last remaining variation (should fail)
    print("\n🧪 TEST 3: Try to delete last remaining variation (should fail)")
    if len(variations) >= 3:
        last_variation = variations[2]
        response = session.delete(f"{BASE_URL}/crm/samples/{sample['id']}/variacoes/{last_variation['id']}")
        if response.status_code == 400:
            print("✅ Correctly blocked deletion of last variation")
            print(f"   Response: {response.json().get('detail', 'No detail')}")
        else:
            print(f"❌ Should have blocked deletion, got: {response.status_code}")
            if response.status_code == 200:
                print(f"   Response: {response.json()}")
    
    # Verify current state
    print("\n📊 Verifying current state...")
    response = session.get(f"{BASE_URL}/crm/samples/{sample['id']}")
    if response.status_code == 200:
        current_sample = response.json()
        current_variations = current_sample.get('variacoes', [])
        print(f"   Current variations: {len(current_variations)}")
        print(f"   Remaining codes: {[v.get('codigo') for v in current_variations]}")
    
    print("\n🏁 Last variation blocking tests complete!")

if __name__ == "__main__":
    test_last_variation_blocking()