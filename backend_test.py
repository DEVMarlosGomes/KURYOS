#!/usr/bin/env python3
"""
Backend Testing for New CRM Delete/Add Endpoints
Testing the new CRM delete and add variation endpoints as requested.
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://approval-pipeline-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kuryos.com"
ADMIN_PASSWORD = "admin123"

class CRMDeleteAddTester:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.test_results = []
        
    def log_test(self, test_name, success, details="", response_data=None):
        """Log test results"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if details:
            print(f"   Details: {details}")
        if not success and response_data:
            print(f"   Response: {response_data}")
        print()

    def authenticate(self):
        """Authenticate with admin credentials"""
        try:
            response = self.session.post(f"{BASE_URL}/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                # Extract token from cookies if available
                if 'access_token' in response.cookies:
                    self.access_token = response.cookies['access_token']
                    self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
                
                self.log_test("Authentication", True, f"Logged in as {data.get('email')}")
                return True
            else:
                self.log_test("Authentication", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Authentication", False, f"Exception: {str(e)}")
            return False

    def create_client(self):
        """Create a test client"""
        try:
            client_data = {
                "nome_empresa": "Test Company for Delete Tests",
                "contato_principal": {
                    "nome": "João Silva",
                    "whatsapp": "+5511999999999",
                    "email": "joao@testcompany.com"
                },
                "canal_origem": "prospeccao_ativa",
                "observacoes": "Cliente criado para testes de delete"
            }
            
            response = self.session.post(f"{BASE_URL}/crm/clients", json=client_data)
            
            if response.status_code in [200, 201]:
                client = response.json()
                self.log_test("Create Client", True, f"Client ID: {client['id']}")
                return client
            else:
                self.log_test("Create Client", False, f"Status: {response.status_code}", response.text)
                return None
        except Exception as e:
            self.log_test("Create Client", False, f"Exception: {str(e)}")
            return None

    def move_client_to_project_stage(self, client_id):
        """Move client through stages to projeto_em_discussao"""
        try:
            # Move to qualificado first
            response = self.session.put(f"{BASE_URL}/crm/clients/{client_id}/move", json={
                "stage": "qualificado"
            })
            
            if response.status_code != 200:
                self.log_test("Move Client to Qualificado", False, f"Status: {response.status_code}", response.text)
                return False
                
            # Move to projeto_em_discussao
            response = self.session.put(f"{BASE_URL}/crm/clients/{client_id}/move", json={
                "stage": "projeto_em_discussao",
                "trigger_batch_projects": True
            })
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Move Client to Projeto em Discussão", True, f"Trigger batch: {data.get('trigger_batch_projects')}")
                return True
            else:
                self.log_test("Move Client to Projeto em Discussão", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Move Client to Projeto em Discussão", False, f"Exception: {str(e)}")
            return False

    def create_project_batch(self, client_id):
        """Create projects via batch endpoint"""
        try:
            projects_data = {
                "cliente_id": client_id,
                "projects": [
                    {
                        "nome_projeto": "Projeto Test Delete 1",
                        "categoria": "perfume",
                        "descricao": "Projeto para teste de delete"
                    },
                    {
                        "nome_projeto": "Projeto Test Delete 2", 
                        "categoria": "hidratante",
                        "descricao": "Segundo projeto para teste"
                    }
                ]
            }
            
            response = self.session.post(f"{BASE_URL}/crm/projects/batch", json=projects_data)
            
            if response.status_code in [200, 201]:
                projects = response.json()
                if isinstance(projects, list) and len(projects) > 0:
                    self.log_test("Create Project Batch", True, f"Created {len(projects)} projects")
                    return projects
                elif isinstance(projects, dict):
                    # If it returns a dict with created array
                    projects_list = projects.get('created', [])
                    if projects_list:
                        self.log_test("Create Project Batch", True, f"Created {len(projects_list)} projects")
                        return projects_list
                    else:
                        self.log_test("Create Project Batch", False, "No projects in response", projects)
                        return None
                else:
                    self.log_test("Create Project Batch", False, "Invalid response format", projects)
                    return None
            else:
                self.log_test("Create Project Batch", False, f"Status: {response.status_code}", response.text)
                return None
        except Exception as e:
            self.log_test("Create Project Batch", False, f"Exception: {str(e)}")
            return None

    def move_project_to_amostras(self, project_id):
        """Move project to amostras stage"""
        try:
            response = self.session.put(f"{BASE_URL}/crm/projects/{project_id}/move", json={
                "stage": "amostras",
                "trigger_batch_samples": True
            })
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Move Project to Amostras", True, f"Trigger batch: {data.get('trigger_batch_samples')}")
                return True
            else:
                self.log_test("Move Project to Amostras", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Move Project to Amostras", False, f"Exception: {str(e)}")
            return False

    def create_sample_with_variations(self, project_id):
        """Create sample with 2 variations using batch/v2 endpoint"""
        try:
            sample_data = {
                "projeto_id": project_id,
                "samples": [
                    {
                        "nome_produto": "Sample Test Delete",
                        "categoria": "perfume",
                        "briefing_base": "Sample criado para teste de delete",
                        "variacoes": [
                            {
                                "descricao_aplicacao": "Variação A para teste",
                                "percentual_fragrancia": 5.0,
                                "referencia_fragrancia": "Ref A",
                                "custo_fragrancia": 10.50,
                                "observacoes_especificas": "Primeira variação"
                            },
                            {
                                "descricao_aplicacao": "Variação B para teste", 
                                "percentual_fragrancia": 7.5,
                                "referencia_fragrancia": "Ref B",
                                "custo_fragrancia": 15.75,
                                "observacoes_especificas": "Segunda variação"
                            }
                        ]
                    }
                ]
            }
            
            response = self.session.post(f"{BASE_URL}/crm/samples/batch/v2", json=sample_data)
            
            if response.status_code in [200, 201]:
                samples = response.json()
                if isinstance(samples, list) and len(samples) > 0:
                    sample = samples[0]
                    self.log_test("Create Sample with Variations", True, 
                                f"Sample ID: {sample['id']}, Variations: {len(sample.get('variacoes', []))}")
                    return sample
                elif isinstance(samples, dict):
                    # If it returns a dict with created array
                    samples_list = samples.get('created', [])
                    if samples_list:
                        sample = samples_list[0]
                        self.log_test("Create Sample with Variations", True, 
                                    f"Sample ID: {sample['id']}, Variations: {len(sample.get('variacoes', []))}")
                        return sample
                    else:
                        self.log_test("Create Sample with Variations", False, "No samples in response", samples)
                        return None
                else:
                    self.log_test("Create Sample with Variations", False, "No sample returned")
                    return None
            else:
                self.log_test("Create Sample with Variations", False, f"Status: {response.status_code}", response.text)
                return None
        except Exception as e:
            self.log_test("Create Sample with Variations", False, f"Exception: {str(e)}")
            return None

    def test_delete_project_cascade(self, project_id):
        """Test DELETE /api/crm/projects/{project_id} - Cascade delete"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/projects/{project_id}")
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Delete Project (Cascade)", True, 
                            f"Deleted project: {data.get('deleted_project')}, "
                            f"Samples: {data.get('deleted_samples')}, "
                            f"PD Cards: {data.get('deleted_pd_cards')}")
                return True
            else:
                self.log_test("Delete Project (Cascade)", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Project (Cascade)", False, f"Exception: {str(e)}")
            return False

    def test_delete_sample_cascade(self, sample_id):
        """Test DELETE /api/crm/samples/{sample_id} - Cascade delete sample"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/samples/{sample_id}")
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Delete Sample (Cascade)", True,
                            f"Deleted sample: {data.get('deleted_sample')}, "
                            f"PD Cards: {data.get('deleted_pd_cards')}")
                return True
            else:
                self.log_test("Delete Sample (Cascade)", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Sample (Cascade)", False, f"Exception: {str(e)}")
            return False

    def test_delete_variation(self, sample_id, variation_id):
        """Test DELETE /api/crm/samples/{sample_id}/variacoes/{variation_id}"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/samples/{sample_id}/variacoes/{variation_id}")
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Delete Variation", True,
                            f"Deleted variation: {data.get('deleted_variacao')} from sample: {data.get('sample_id')}")
                return True
            else:
                self.log_test("Delete Variation", False, f"Status: {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Variation", False, f"Exception: {str(e)}")
            return False

    def test_delete_last_variation_should_fail(self, sample_id, variation_id):
        """Test that deleting the last variation should return 400"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/samples/{sample_id}/variacoes/{variation_id}")
            
            if response.status_code == 400:
                self.log_test("Delete Last Variation (Should Fail)", True, "Correctly blocked deletion of last variation")
                return True
            else:
                self.log_test("Delete Last Variation (Should Fail)", False, 
                            f"Expected 400, got {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Last Variation (Should Fail)", False, f"Exception: {str(e)}")
            return False

    def test_add_variations_to_sample(self, sample_id):
        """Test POST /api/crm/samples/{sample_id}/variacoes - Add variations to existing sample"""
        try:
            new_variations_data = {
                "variacoes": [
                    {
                        "descricao_aplicacao": "Test C Variation",
                        "percentual_fragrancia": 3.0,
                        "referencia_fragrancia": "Ref C",
                        "custo_fragrancia": 8.25,
                        "observacoes_especificas": "Third variation added"
                    },
                    {
                        "descricao_aplicacao": "Test D Variation",
                        "percentual_fragrancia": 4.5,
                        "referencia_fragrancia": "Ref D", 
                        "custo_fragrancia": 12.00,
                        "observacoes_especificas": "Fourth variation added"
                    }
                ]
            }
            
            response = self.session.post(f"{BASE_URL}/crm/samples/{sample_id}/variacoes", json=new_variations_data)
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.log_test("Add Variations to Sample", True,
                            f"Added {len(data.get('new_variacoes', []))} variations. "
                            f"Total variations: {data.get('total_variacoes')}")
                return data
            else:
                self.log_test("Add Variations to Sample", False, f"Status: {response.status_code}", response.text)
                return None
        except Exception as e:
            self.log_test("Add Variations to Sample", False, f"Exception: {str(e)}")
            return None

    def approve_variation_to_create_sku(self, sample_id, variation_id):
        """Approve a variation to create SKU for blocking tests"""
        try:
            # Move variation through stages to approved
            stages = ["em_elaboracao", "enviada", "aprovada"]
            
            for stage in stages:
                response = self.session.put(f"{BASE_URL}/crm/samples/{sample_id}/variacoes/{variation_id}/move", json={
                    "status": stage
                })
                
                if response.status_code != 200:
                    self.log_test(f"Move Variation to {stage}", False, f"Status: {response.status_code}", response.text)
                    return False
                    
            self.log_test("Approve Variation (Create SKU)", True, f"Variation {variation_id} approved and SKU created")
            return True
        except Exception as e:
            self.log_test("Approve Variation (Create SKU)", False, f"Exception: {str(e)}")
            return False

    def test_delete_project_with_sku_should_fail(self, project_id):
        """Test that deleting project with SKU should return 400"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/projects/{project_id}")
            
            if response.status_code == 400:
                self.log_test("Delete Project with SKU (Should Fail)", True, "Correctly blocked deletion of project with SKU")
                return True
            else:
                self.log_test("Delete Project with SKU (Should Fail)", False,
                            f"Expected 400, got {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Project with SKU (Should Fail)", False, f"Exception: {str(e)}")
            return False

    def test_delete_sample_with_sku_should_fail(self, sample_id):
        """Test that deleting sample with SKU should return 400"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/samples/{sample_id}")
            
            if response.status_code == 400:
                self.log_test("Delete Sample with SKU (Should Fail)", True, "Correctly blocked deletion of sample with SKU")
                return True
            else:
                self.log_test("Delete Sample with SKU (Should Fail)", False,
                            f"Expected 400, got {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Sample with SKU (Should Fail)", False, f"Exception: {str(e)}")
            return False

    def test_delete_variation_with_sku_should_fail(self, sample_id, variation_id):
        """Test that deleting variation with SKU should return 400"""
        try:
            response = self.session.delete(f"{BASE_URL}/crm/samples/{sample_id}/variacoes/{variation_id}")
            
            if response.status_code == 400:
                self.log_test("Delete Variation with SKU (Should Fail)", True, "Correctly blocked deletion of variation with SKU")
                return True
            else:
                self.log_test("Delete Variation with SKU (Should Fail)", False,
                            f"Expected 400, got {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_test("Delete Variation with SKU (Should Fail)", False, f"Exception: {str(e)}")
            return False

    def verify_pd_cards_created(self, sample):
        """Verify that PD cards were created for variations"""
        try:
            response = self.session.get(f"{BASE_URL}/crm/pd/cards")
            
            if response.status_code == 200:
                pd_cards = response.json()
                sample_pd_cards = []
                
                for variation in sample.get('variacoes', []):
                    if variation.get('pd_card_id'):
                        # Find the PD card
                        pd_card = next((card for card in pd_cards if card['id'] == variation['pd_card_id']), None)
                        if pd_card:
                            sample_pd_cards.append(pd_card)
                
                self.log_test("Verify PD Cards Created", True, 
                            f"Found {len(sample_pd_cards)} PD cards for {len(sample.get('variacoes', []))} variations")
                return sample_pd_cards
            else:
                self.log_test("Verify PD Cards Created", False, f"Status: {response.status_code}", response.text)
                return []
        except Exception as e:
            self.log_test("Verify PD Cards Created", False, f"Exception: {str(e)}")
            return []

    def run_comprehensive_test(self):
        """Run the comprehensive test suite for CRM delete/add endpoints"""
        print("🧪 Starting CRM Delete/Add Endpoints Testing")
        print("=" * 60)
        
        # Authenticate
        if not self.authenticate():
            return
            
        # Test 1: DELETE /api/crm/projects/{project_id} — Cascade delete
        print("\n📋 TEST 1: Project Cascade Delete")
        print("-" * 40)
        
        client = self.create_client()
        if not client:
            return
            
        if not self.move_client_to_project_stage(client['id']):
            return
            
        projects = self.create_project_batch(client['id'])
        if not projects or len(projects) == 0:
            return
            
        project = projects[0]
        if not self.move_project_to_amostras(project['id']):
            return
            
        sample = self.create_sample_with_variations(project['id'])
        if not sample:
            return
            
        # Verify PD cards were created
        self.verify_pd_cards_created(sample)
        
        # Test cascade delete
        self.test_delete_project_cascade(project['id'])
        
        # Test 2: SKU Block test for project delete
        print("\n📋 TEST 2: Project Delete with SKU Block")
        print("-" * 40)
        
        # Create new setup for SKU test
        client2 = self.create_client()
        if not client2:
            return
            
        if not self.move_client_to_project_stage(client2['id']):
            return
            
        projects2 = self.create_project_batch(client2['id'])
        if not projects2:
            return
            
        project2 = projects2[0]
        if not self.move_project_to_amostras(project2['id']):
            return
            
        sample2 = self.create_sample_with_variations(project2['id'])
        if not sample2:
            return
            
        # Approve one variation to create SKU
        if sample2.get('variacoes'):
            variation = sample2['variacoes'][0]
            if self.approve_variation_to_create_sku(sample2['id'], variation['id']):
                # Now try to delete project - should fail
                self.test_delete_project_with_sku_should_fail(project2['id'])
        
        # Test 3: DELETE /api/crm/samples/{sample_id} — Cascade delete sample
        print("\n📋 TEST 3: Sample Cascade Delete")
        print("-" * 40)
        
        # Create new sample for this test
        client3 = self.create_client()
        if not client3:
            return
            
        if not self.move_client_to_project_stage(client3['id']):
            return
            
        projects3 = self.create_project_batch(client3['id'])
        if not projects3:
            return
            
        project3 = projects3[0]
        if not self.move_project_to_amostras(project3['id']):
            return
            
        sample3 = self.create_sample_with_variations(project3['id'])
        if not sample3:
            return
            
        # Test sample cascade delete
        self.test_delete_sample_cascade(sample3['id'])
        
        # Test 4: Sample delete with SKU block
        print("\n📋 TEST 4: Sample Delete with SKU Block")
        print("-" * 40)
        
        # Use the sample from test 2 that has SKU
        if sample2:
            self.test_delete_sample_with_sku_should_fail(sample2['id'])
        
        # Test 5: DELETE /api/crm/samples/{sample_id}/variacoes/{variacao_id} — Delete single variation
        print("\n📋 TEST 5: Single Variation Delete")
        print("-" * 40)
        
        # Create new sample with 3 variations for this test
        client4 = self.create_client()
        if not client4:
            return
            
        if not self.move_client_to_project_stage(client4['id']):
            return
            
        projects4 = self.create_project_batch(client4['id'])
        if not projects4:
            return
            
        project4 = projects4[0]
        if not self.move_project_to_amostras(project4['id']):
            return
            
        # Create sample with 2 variations first
        sample4 = self.create_sample_with_variations(project4['id'])
        if not sample4:
            return
            
        # Add one more variation to have 3 total
        add_result = self.test_add_variations_to_sample(sample4['id'])
        if not add_result:
            return
            
        # Get updated sample info
        response = self.session.get(f"{BASE_URL}/crm/samples/{sample4['id']}")
        if response.status_code == 200:
            updated_sample = response.json()
            variations = updated_sample.get('variacoes', [])
            
            if len(variations) >= 3:
                # Delete one variation (should succeed)
                self.test_delete_variation(sample4['id'], variations[1]['id'])
                
                # Try to delete another (should succeed, leaving 1)
                self.test_delete_variation(sample4['id'], variations[2]['id'])
                
                # Try to delete the last one (should fail)
                self.test_delete_last_variation_should_fail(sample4['id'], variations[0]['id'])
        
        # Test 6: Variation delete with SKU block
        print("\n📋 TEST 6: Variation Delete with SKU Block")
        print("-" * 40)
        
        # Use variation from test 2 that has SKU
        if sample2 and sample2.get('variacoes'):
            approved_variation = sample2['variacoes'][0]
            self.test_delete_variation_with_sku_should_fail(sample2['id'], approved_variation['id'])
        
        # Test 7: POST /api/crm/samples/{sample_id}/variacoes — Add variations to existing sample
        print("\n📋 TEST 7: Add Variations to Existing Sample")
        print("-" * 40)
        
        # Create new sample for this test
        client5 = self.create_client()
        if not client5:
            return
            
        if not self.move_client_to_project_stage(client5['id']):
            return
            
        projects5 = self.create_project_batch(client5['id'])
        if not projects5:
            return
            
        project5 = projects5[0]
        if not self.move_project_to_amostras(project5['id']):
            return
            
        sample5 = self.create_sample_with_variations(project5['id'])
        if not sample5:
            return
            
        # Add new variations
        self.test_add_variations_to_sample(sample5['id'])
        
        # Verify final state
        response = self.session.get(f"{BASE_URL}/crm/samples/{sample5['id']}")
        if response.status_code == 200:
            final_sample = response.json()
            variations = final_sample.get('variacoes', [])
            self.log_test("Verify Final Sample State", True,
                        f"Sample has {len(variations)} variations with codes: {[v.get('codigo') for v in variations]}")
            
            # Verify PD cards for new variations
            self.verify_pd_cards_created(final_sample)

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("🏁 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"   - {result['test']}: {result['details']}")
        
        print(f"\n📊 DETAILED RESULTS:")
        for result in self.test_results:
            status = "✅" if result['success'] else "❌"
            print(f"   {status} {result['test']}")

if __name__ == "__main__":
    tester = CRMDeleteAddTester()
    tester.run_comprehensive_test()
    tester.print_summary()