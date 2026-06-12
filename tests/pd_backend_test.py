#!/usr/bin/env python3
"""
P&D Backend Test Suite for New Modules
Tests 4 new P&D feature modules: Cost Catalog, Internal Research, Lab Stock, Updates & Pending
"""

import requests
import json
import sys
from datetime import datetime, timezone, timedelta

# Configuration
BASE_URL = "https://approval-pipeline-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kuryos.com"
ADMIN_PASSWORD = "admin123"

class PDTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.test_results = []
        self.catalog_item_id = None
        self.internal_research_id = None
        self.pd_card_id = None
        self.stock_item_id = None
        self.stock_item_id_2 = None
        self.update_id = None
        self.pending_id = None
        
    def log_test(self, test_name, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'success': success,
            'details': details
        })
        print(f"{status}: {test_name}")
        if details and not success:
            print(f"   Details: {details}")
    
    def login(self):
        """Authenticate with admin credentials"""
        try:
            response = self.session.post(f"{BASE_URL}/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
            
            if response.status_code == 200:
                self.log_test("Authentication", True, "Admin login successful")
                return True
            else:
                self.log_test("Authentication", False, f"Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.log_test("Authentication", False, f"Login error: {str(e)}")
            return False
    
    # ============ 1) P&D COST CATALOG (BANCO DE CUSTOS) ============
    
    def test_create_catalog_item(self):
        """Test POST /api/pd/catalog"""
        try:
            catalog_data = {
                "nome": "Álcool Etílico 96%",
                "inci": "Alcohol Denat.",
                "fornecedor": "Química Moderna",
                "preco_rs_kg": 10.50,
                "moeda": "BRL",
                "unidade": "L",
                "categoria": "solvente",
                "observacoes": "Álcool de alta pureza para cosméticos"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/catalog", json=catalog_data)
            
            if response.status_code == 200:
                data = response.json()
                self.catalog_item_id = data.get('id')
                
                # Validate response structure
                required_fields = ['id', 'nome', 'preco_rs_kg', 'ultima_atualizacao']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Create Catalog Item", False, f"Missing fields: {missing_fields}")
                elif data.get('nome') != "Álcool Etílico 96%" or data.get('preco_rs_kg') != 10.50:
                    self.log_test("Create Catalog Item", False, "Data not saved correctly")
                else:
                    self.log_test("Create Catalog Item", True, f"Catalog item created with ID: {self.catalog_item_id}")
                return True
            else:
                self.log_test("Create Catalog Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Catalog Item", False, f"Error: {str(e)}")
            return False
    
    def test_list_catalog(self):
        """Test GET /api/pd/catalog with search and filter"""
        try:
            # Test list all
            response = self.session.get(f"{BASE_URL}/pd/catalog")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.log_test("List Catalog Items", True, f"Retrieved {len(data)} catalog items")
                else:
                    self.log_test("List Catalog Items", False, "No catalog items returned")
                    return False
            else:
                self.log_test("List Catalog Items", False, f"Status: {response.status_code}")
                return False
            
            # Test search by name
            response = self.session.get(f"{BASE_URL}/pd/catalog?q=Álcool")
            if response.status_code == 200:
                data = response.json()
                if len(data) > 0 and any("Álcool" in item.get('nome', '') for item in data):
                    self.log_test("Search Catalog by Name", True, f"Found {len(data)} items matching 'Álcool'")
                else:
                    self.log_test("Search Catalog by Name", False, "Search didn't return expected results")
            else:
                self.log_test("Search Catalog by Name", False, f"Status: {response.status_code}")
                return False
            
            # Test filter by category
            response = self.session.get(f"{BASE_URL}/pd/catalog?categoria=solvente")
            if response.status_code == 200:
                data = response.json()
                if len(data) > 0:
                    self.log_test("Filter Catalog by Category", True, f"Found {len(data)} solvente items")
                else:
                    self.log_test("Filter Catalog by Category", False, "No items found for category filter")
            else:
                self.log_test("Filter Catalog by Category", False, f"Status: {response.status_code}")
                return False
            
            return True
        except Exception as e:
            self.log_test("List Catalog", False, f"Error: {str(e)}")
            return False
    
    def test_get_catalog_item(self):
        """Test GET /api/pd/catalog/{id}"""
        if not self.catalog_item_id:
            self.log_test("Get Catalog Item", False, "No catalog item ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/catalog/{self.catalog_item_id}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('id') == self.catalog_item_id and data.get('nome') == "Álcool Etílico 96%":
                    self.log_test("Get Catalog Item", True, f"Retrieved catalog item: {data.get('nome')}")
                else:
                    self.log_test("Get Catalog Item", False, "Item data mismatch")
                return True
            else:
                self.log_test("Get Catalog Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Get Catalog Item", False, f"Error: {str(e)}")
            return False
    
    def test_update_catalog_item_price(self):
        """Test PUT /api/pd/catalog/{id} - update price to trigger history"""
        if not self.catalog_item_id:
            self.log_test("Update Catalog Item Price", False, "No catalog item ID available")
            return False
            
        try:
            update_data = {
                "preco_rs_kg": 15.00,
                "observacoes": "Preço atualizado devido ao aumento do fornecedor"
            }
            
            response = self.session.put(f"{BASE_URL}/pd/catalog/{self.catalog_item_id}", json=update_data)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('preco_rs_kg') == 15.00 and 'ultima_atualizacao' in data:
                    self.log_test("Update Catalog Item Price", True, f"Price updated from 10.50 to 15.00")
                else:
                    self.log_test("Update Catalog Item Price", False, "Update data not reflected")
                return True
            else:
                self.log_test("Update Catalog Item Price", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Update Catalog Item Price", False, f"Error: {str(e)}")
            return False
    
    def test_catalog_price_history(self):
        """Test GET /api/pd/catalog/{id}/price-history"""
        if not self.catalog_item_id:
            self.log_test("Catalog Price History", False, "No catalog item ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/catalog/{self.catalog_item_id}/price-history")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # Should have history entry showing change from 10.50 to 15.00
                    history_entry = data[0]  # Most recent
                    if (history_entry.get('preco_anterior') == 10.50 and 
                        history_entry.get('preco_novo') == 15.00):
                        self.log_test("Catalog Price History", True, f"Price history shows change: 10.50 → 15.00")
                    else:
                        self.log_test("Catalog Price History", False, f"Price history data incorrect: {history_entry}")
                else:
                    self.log_test("Catalog Price History", False, "No price history found")
                return True
            else:
                self.log_test("Catalog Price History", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Catalog Price History", False, f"Error: {str(e)}")
            return False
    
    def test_delete_catalog_item(self):
        """Test DELETE /api/pd/catalog/{id}"""
        if not self.catalog_item_id:
            self.log_test("Delete Catalog Item", False, "No catalog item ID available")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/pd/catalog/{self.catalog_item_id}")
            
            if response.status_code == 200:
                # Verify item is deleted
                verify_response = self.session.get(f"{BASE_URL}/pd/catalog/{self.catalog_item_id}")
                if verify_response.status_code == 404:
                    self.log_test("Delete Catalog Item", True, "Catalog item successfully deleted")
                else:
                    self.log_test("Delete Catalog Item", False, "Item still exists after deletion")
                return True
            else:
                self.log_test("Delete Catalog Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Delete Catalog Item", False, f"Error: {str(e)}")
            return False
    
    # ============ 2) P&D INTERNAL RESEARCH (PESQUISA INTERNA) ============
    
    def test_create_internal_research(self):
        """Test POST /api/pd/requests/internal-research"""
        try:
            research_data = {
                "project_name": "Teste Pesquisa Interna - Novo Hidratante",
                "objectives": "Desenvolver hidratante com textura inovadora",
                "description": "Pesquisa para criar hidratante com absorção ultra-rápida",
                "category": "skin_care",
                "priority": "Normal"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/requests/internal-research", json=research_data)
            
            if response.status_code == 200:
                data = response.json()
                self.internal_research_id = data.get('id')
                self.pd_card_id = data.get('pd_card_id')
                
                # Validate response structure
                required_fields = ['id', 'is_internal_research', 'status', 'client_name', 'pd_card_id']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Create Internal Research", False, f"Missing fields: {missing_fields}")
                elif (data.get('is_internal_research') != True or 
                      data.get('status') != 'IN_PROGRESS' or 
                      data.get('client_name') != '— Pesquisa Interna —'):
                    self.log_test("Create Internal Research", False, f"Incorrect data: is_internal_research={data.get('is_internal_research')}, status={data.get('status')}, client_name={data.get('client_name')}")
                else:
                    self.log_test("Create Internal Research", True, f"Internal research created with ID: {self.internal_research_id}, pd_card_id: {self.pd_card_id}")
                return True
            else:
                self.log_test("Create Internal Research", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Internal Research", False, f"Error: {str(e)}")
            return False
    
    def test_verify_pd_card_created(self):
        """Test that pd_card was auto-created with PI-XXX pattern"""
        if not self.pd_card_id:
            self.log_test("Verify PD Card Created", False, "No pd_card_id available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/crm/pd/cards/{self.pd_card_id}")
            
            if response.status_code == 200:
                data = response.json()
                numero_completo = data.get('numero_completo', '')
                tipo = data.get('tipo', '')
                status_pd = data.get('status_pd', '')
                pd_request_id = data.get('pd_request_id', '')
                
                if (numero_completo.startswith('PI-') and 
                    tipo == 'pesquisa_interna' and 
                    status_pd == 'em_desenvolvimento' and 
                    pd_request_id == self.internal_research_id):
                    self.log_test("Verify PD Card Created", True, f"PD Card created: {numero_completo}, linked to pd_request")
                else:
                    self.log_test("Verify PD Card Created", False, f"PD Card data incorrect: numero={numero_completo}, tipo={tipo}, status={status_pd}, linked={pd_request_id}")
                return True
            else:
                self.log_test("Verify PD Card Created", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Verify PD Card Created", False, f"Error: {str(e)}")
            return False
    
    def test_verify_development_created(self):
        """Test that development was auto-created"""
        if not self.internal_research_id:
            self.log_test("Verify Development Created", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/development")
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('pd_request_id') == self.internal_research_id and 
                    data.get('status') == 'active'):
                    self.log_test("Verify Development Created", True, f"Development auto-created for internal research")
                else:
                    self.log_test("Verify Development Created", False, "Development data incorrect")
                return True
            else:
                self.log_test("Verify Development Created", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Verify Development Created", False, f"Error: {str(e)}")
            return False
    
    def test_list_internal_research(self):
        """Test GET /api/pd/requests/internal-research/list"""
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/internal-research/list")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # Should find our created internal research
                    found = any(item.get('id') == self.internal_research_id for item in data)
                    if found:
                        self.log_test("List Internal Research", True, f"Found {len(data)} internal research requests")
                    else:
                        self.log_test("List Internal Research", False, "Created internal research not found in list")
                else:
                    self.log_test("List Internal Research", False, "No internal research requests returned")
                return True
            else:
                self.log_test("List Internal Research", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("List Internal Research", False, f"Error: {str(e)}")
            return False
    
    def test_verify_pd_cards_includes_pi(self):
        """Test GET /api/crm/pd/cards includes the new PI card"""
        try:
            response = self.session.get(f"{BASE_URL}/crm/pd/cards")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    # Should find our PI card
                    found = any(card.get('id') == self.pd_card_id for card in data)
                    if found:
                        self.log_test("Verify PD Cards Includes PI", True, f"PI card found in PD cards list ({len(data)} total cards)")
                    else:
                        self.log_test("Verify PD Cards Includes PI", False, "PI card not found in PD cards list")
                else:
                    self.log_test("Verify PD Cards Includes PI", False, "Invalid response format")
                return True
            else:
                self.log_test("Verify PD Cards Includes PI", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Verify PD Cards Includes PI", False, f"Error: {str(e)}")
            return False
    
    # ============ 3) P&D LAB STOCK (ESTOQUE) ============
    
    def test_create_stock_mp_item(self):
        """Test POST /api/pd/stock - create MP item"""
        try:
            stock_data = {
                "categoria": "mp",
                "nome": "Álcool 96%",
                "quantidade_atual": 50.0,
                "quantidade_minima": 10.0,
                "lote": "L001",
                "unidade_medida": "L",
                "custo_unitario": 12.50,
                "fornecedor": "Química Moderna",
                "observacoes": "Álcool para formulações"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock", json=stock_data)
            
            if response.status_code == 200:
                data = response.json()
                self.stock_item_id = data.get('id')
                
                # Validate response structure
                required_fields = ['id', 'categoria', 'nome', 'quantidade_atual', 'quantidade_minima']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Create Stock MP Item", False, f"Missing fields: {missing_fields}")
                elif (data.get('categoria') != 'mp' or 
                      data.get('quantidade_atual') != 50.0 or 
                      data.get('lote') != 'L001'):
                    self.log_test("Create Stock MP Item", False, "Data not saved correctly")
                else:
                    self.log_test("Create Stock MP Item", True, f"MP stock item created with ID: {self.stock_item_id}")
                return True
            else:
                self.log_test("Create Stock MP Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Stock MP Item", False, f"Error: {str(e)}")
            return False
    
    def test_create_stock_amostra_acabada(self):
        """Test POST /api/pd/stock - create Amostra Acabada item"""
        try:
            stock_data = {
                "categoria": "amostra_acabada",
                "nome": "Body Splash La Vie 3%",
                "quantidade_atual": 20.0,
                "quantidade_minima": 5.0,
                "unidade_medida": "un",
                "fragrancia_percentual": 3.0,
                "formula_ref": "Body Splash La Vie v2",
                "observacoes": "Amostra acabada para testes"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock", json=stock_data)
            
            if response.status_code == 200:
                data = response.json()
                self.stock_item_id_2 = data.get('id')
                
                if (data.get('categoria') == 'amostra_acabada' and 
                    data.get('fragrancia_percentual') == 3.0 and 
                    data.get('formula_ref') == 'Body Splash La Vie v2'):
                    self.log_test("Create Stock Amostra Acabada", True, f"Amostra Acabada created with ID: {self.stock_item_id_2}")
                else:
                    self.log_test("Create Stock Amostra Acabada", False, "Data not saved correctly")
                return True
            else:
                self.log_test("Create Stock Amostra Acabada", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Stock Amostra Acabada", False, f"Error: {str(e)}")
            return False
    
    def test_list_stock_with_filter(self):
        """Test GET /api/pd/stock with category filter"""
        try:
            # Test list all
            response = self.session.get(f"{BASE_URL}/pd/stock")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) >= 2:
                    self.log_test("List All Stock", True, f"Retrieved {len(data)} stock items")
                else:
                    self.log_test("List All Stock", False, f"Expected at least 2 items, got {len(data) if isinstance(data, list) else 'invalid format'}")
                    return False
            else:
                self.log_test("List All Stock", False, f"Status: {response.status_code}")
                return False
            
            # Test filter by category
            response = self.session.get(f"{BASE_URL}/pd/stock?categoria=mp")
            if response.status_code == 200:
                data = response.json()
                if len(data) > 0 and all(item.get('categoria') == 'mp' for item in data):
                    self.log_test("Filter Stock by Category", True, f"Found {len(data)} MP items")
                else:
                    self.log_test("Filter Stock by Category", False, "Category filter not working correctly")
            else:
                self.log_test("Filter Stock by Category", False, f"Status: {response.status_code}")
                return False
            
            return True
        except Exception as e:
            self.log_test("List Stock", False, f"Error: {str(e)}")
            return False
    
    def test_stock_movement_saida(self):
        """Test POST /api/pd/stock/{id}/movements - saida"""
        if not self.stock_item_id:
            self.log_test("Stock Movement Saida", False, "No stock item ID available")
            return False
            
        try:
            movement_data = {
                "tipo": "saida",
                "quantidade": 5.0,
                "motivo": "Uso em formulação teste"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock/{self.stock_item_id}/movements", json=movement_data)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('tipo') == 'saida' and 
                    data.get('quantidade') == 5.0 and 
                    data.get('quantidade_antes') == 50.0 and 
                    data.get('quantidade_depois') == 45.0):
                    self.log_test("Stock Movement Saida", True, f"Saida movement: 50 → 45 (removed 5)")
                else:
                    self.log_test("Stock Movement Saida", False, f"Movement data incorrect: {data}")
                return True
            else:
                self.log_test("Stock Movement Saida", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Stock Movement Saida", False, f"Error: {str(e)}")
            return False
    
    def test_stock_movement_entrada(self):
        """Test POST /api/pd/stock/{id}/movements - entrada"""
        if not self.stock_item_id:
            self.log_test("Stock Movement Entrada", False, "No stock item ID available")
            return False
            
        try:
            movement_data = {
                "tipo": "entrada",
                "quantidade": 10.0,
                "motivo": "Reposição de estoque"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock/{self.stock_item_id}/movements", json=movement_data)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('tipo') == 'entrada' and 
                    data.get('quantidade') == 10.0 and 
                    data.get('quantidade_antes') == 45.0 and 
                    data.get('quantidade_depois') == 55.0):
                    self.log_test("Stock Movement Entrada", True, f"Entrada movement: 45 → 55 (added 10)")
                else:
                    self.log_test("Stock Movement Entrada", False, f"Movement data incorrect: {data}")
                return True
            else:
                self.log_test("Stock Movement Entrada", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Stock Movement Entrada", False, f"Error: {str(e)}")
            return False
    
    def test_stock_movement_invalid_saida(self):
        """Test POST /api/pd/stock/{id}/movements - saida maior que estoque (should fail)"""
        if not self.stock_item_id:
            self.log_test("Stock Movement Invalid Saida", False, "No stock item ID available")
            return False
            
        try:
            movement_data = {
                "tipo": "saida",
                "quantidade": 1000.0,
                "motivo": "Tentativa de saída inválida"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock/{self.stock_item_id}/movements", json=movement_data)
            
            if response.status_code == 400:
                self.log_test("Stock Movement Invalid Saida", True, "Invalid saida correctly rejected (quantity > stock)")
                return True
            else:
                self.log_test("Stock Movement Invalid Saida", False, f"Expected 400, got {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Stock Movement Invalid Saida", False, f"Error: {str(e)}")
            return False
    
    def test_stock_movement_ajuste(self):
        """Test POST /api/pd/stock/{id}/movements - ajuste (absolute quantity)"""
        if not self.stock_item_id:
            self.log_test("Stock Movement Ajuste", False, "No stock item ID available")
            return False
            
        try:
            movement_data = {
                "tipo": "ajuste",
                "quantidade": 30.0,
                "motivo": "Ajuste de inventário"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock/{self.stock_item_id}/movements", json=movement_data)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('tipo') == 'ajuste' and 
                    data.get('quantidade') == 30.0 and 
                    data.get('quantidade_depois') == 30.0):
                    self.log_test("Stock Movement Ajuste", True, f"Ajuste movement: quantity set to 30")
                else:
                    self.log_test("Stock Movement Ajuste", False, f"Movement data incorrect: {data}")
                return True
            else:
                self.log_test("Stock Movement Ajuste", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Stock Movement Ajuste", False, f"Error: {str(e)}")
            return False
    
    def test_list_stock_movements(self):
        """Test GET /api/pd/stock/{id}/movements"""
        if not self.stock_item_id:
            self.log_test("List Stock Movements", False, "No stock item ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/stock/{self.stock_item_id}/movements")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) >= 4:  # entrada inicial + saida + entrada + ajuste
                    # Check if movements are in descending order (most recent first)
                    movements_sorted = all(
                        data[i].get('created_at', '') >= data[i+1].get('created_at', '') 
                        for i in range(len(data)-1)
                    )
                    
                    # Check if all movements have quantidade_antes and quantidade_depois
                    all_have_quantities = all(
                        'quantidade_antes' in mov and 'quantidade_depois' in mov 
                        for mov in data
                    )
                    
                    if movements_sorted and all_have_quantities:
                        self.log_test("List Stock Movements", True, f"Retrieved {len(data)} movements in correct order with quantity tracking")
                    else:
                        self.log_test("List Stock Movements", False, "Movements not properly sorted or missing quantity data")
                else:
                    self.log_test("List Stock Movements", False, f"Expected at least 4 movements, got {len(data) if isinstance(data, list) else 'invalid format'}")
                return True
            else:
                self.log_test("List Stock Movements", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("List Stock Movements", False, f"Error: {str(e)}")
            return False
    
    def test_stock_alerts(self):
        """Test GET /api/pd/stock/alerts - create low stock item and verify alert"""
        try:
            # First create an item with low stock
            low_stock_data = {
                "categoria": "mp",
                "nome": "Ingrediente Baixo Estoque",
                "quantidade_atual": 5.0,
                "quantidade_minima": 10.0,
                "unidade_medida": "kg"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/stock", json=low_stock_data)
            if response.status_code != 200:
                self.log_test("Stock Alerts", False, "Failed to create low stock item")
                return False
            
            low_stock_item_id = response.json().get('id')
            
            # Now check alerts
            response = self.session.get(f"{BASE_URL}/pd/stock/alerts")
            
            if response.status_code == 200:
                data = response.json()
                if 'low_stock' in data and 'expiring' in data:
                    low_stock_items = data['low_stock']
                    found_low_stock = any(item.get('id') == low_stock_item_id for item in low_stock_items)
                    
                    if found_low_stock:
                        self.log_test("Stock Alerts", True, f"Low stock alert working: {len(low_stock_items)} low stock items found")
                    else:
                        self.log_test("Stock Alerts", False, "Low stock item not found in alerts")
                else:
                    self.log_test("Stock Alerts", False, "Missing low_stock or expiring keys in response")
                return True
            else:
                self.log_test("Stock Alerts", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Stock Alerts", False, f"Error: {str(e)}")
            return False
    
    def test_update_stock_item(self):
        """Test PUT /api/pd/stock/{id} - update fields (not quantidade_atual)"""
        if not self.stock_item_id:
            self.log_test("Update Stock Item", False, "No stock item ID available")
            return False
            
        try:
            update_data = {
                "observacoes": "Observações atualizadas",
                "custo_unitario": 15.00,
                "localizacao": "Prateleira A-3"
            }
            
            response = self.session.put(f"{BASE_URL}/pd/stock/{self.stock_item_id}", json=update_data)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('observacoes') == "Observações atualizadas" and 
                    data.get('custo_unitario') == 15.00 and 
                    data.get('localizacao') == "Prateleira A-3"):
                    self.log_test("Update Stock Item", True, "Stock item updated successfully")
                else:
                    self.log_test("Update Stock Item", False, "Update data not reflected")
                return True
            else:
                self.log_test("Update Stock Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Update Stock Item", False, f"Error: {str(e)}")
            return False
    
    def test_delete_stock_item(self):
        """Test DELETE /api/pd/stock/{id} - verify deletes item and movements"""
        if not self.stock_item_id_2:
            self.log_test("Delete Stock Item", False, "No stock item ID available")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/pd/stock/{self.stock_item_id_2}")
            
            if response.status_code == 200:
                # Verify item is deleted
                verify_response = self.session.get(f"{BASE_URL}/pd/stock/{self.stock_item_id_2}")
                if verify_response.status_code == 404:
                    self.log_test("Delete Stock Item", True, "Stock item and movements successfully deleted")
                else:
                    self.log_test("Delete Stock Item", False, "Item still exists after deletion")
                return True
            else:
                self.log_test("Delete Stock Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Delete Stock Item", False, f"Error: {str(e)}")
            return False
    
    # ============ 4) P&D UPDATES & PENDING ITEMS (ATUALIZAÇÕES) ============
    
    def test_create_update(self):
        """Test POST /api/pd/requests/{req_id}/updates"""
        if not self.internal_research_id:
            self.log_test("Create Update", False, "No internal research ID available")
            return False
            
        try:
            update_data = {
                "mensagem": "Testando atualização do desenvolvimento",
                "tipo": "observacao",
                "visivel_comercial": True
            }
            
            response = self.session.post(f"{BASE_URL}/pd/requests/{self.internal_research_id}/updates", json=update_data)
            
            if response.status_code == 200:
                data = response.json()
                self.update_id = data.get('id')
                
                if (data.get('mensagem') == "Testando atualização do desenvolvimento" and 
                    data.get('tipo') == 'observacao' and 
                    data.get('visivel_comercial') == True):
                    self.log_test("Create Update", True, f"Update created with ID: {self.update_id}")
                else:
                    self.log_test("Create Update", False, "Update data not saved correctly")
                return True
            else:
                self.log_test("Create Update", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Update", False, f"Error: {str(e)}")
            return False
    
    def test_list_updates(self):
        """Test GET /api/pd/requests/{req_id}/updates"""
        if not self.internal_research_id:
            self.log_test("List Updates", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/updates")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # Should find our created update
                    found = any(update.get('id') == self.update_id for update in data)
                    if found:
                        self.log_test("List Updates", True, f"Found {len(data)} updates including created one")
                    else:
                        self.log_test("List Updates", False, "Created update not found in list")
                else:
                    self.log_test("List Updates", False, "No updates returned")
                return True
            else:
                self.log_test("List Updates", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("List Updates", False, f"Error: {str(e)}")
            return False
    
    def test_create_pending_item(self):
        """Test POST /api/pd/requests/{req_id}/pending"""
        if not self.internal_research_id:
            self.log_test("Create Pending Item", False, "No internal research ID available")
            return False
            
        try:
            pending_data = {
                "tipo": "fragrancia",
                "descricao": "Fragrância Ginger Premium",
                "data_prevista": "2025-12-31T00:00:00+00:00",
                "fornecedor": "Givaudan",
                "observacoes": "Fragrância especial para linha premium"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/requests/{self.internal_research_id}/pending", json=pending_data)
            
            if response.status_code == 200:
                data = response.json()
                self.pending_id = data.get('id')
                
                if (data.get('tipo') == 'fragrancia' and 
                    data.get('descricao') == 'Fragrância Ginger Premium' and 
                    data.get('status') == 'pendente' and 
                    data.get('fornecedor') == 'Givaudan'):
                    self.log_test("Create Pending Item", True, f"Pending item created with ID: {self.pending_id}")
                else:
                    self.log_test("Create Pending Item", False, "Pending item data not saved correctly")
                return True
            else:
                self.log_test("Create Pending Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Create Pending Item", False, f"Error: {str(e)}")
            return False
    
    def test_verify_system_update_created(self):
        """Test that creating pending item auto-created a system update"""
        if not self.internal_research_id:
            self.log_test("Verify System Update Created", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/updates")
            
            if response.status_code == 200:
                data = response.json()
                # Should have at least 2 updates now (our manual one + auto-created from pending)
                if len(data) >= 2:
                    # Look for system update about pending creation
                    system_update = next((u for u in data if u.get('tipo') == 'pendencia_criada'), None)
                    if system_update and 'Fragrância Ginger' in system_update.get('mensagem', ''):
                        self.log_test("Verify System Update Created", True, "System update auto-created for pending item")
                    else:
                        self.log_test("Verify System Update Created", False, "System update not found or incorrect")
                else:
                    self.log_test("Verify System Update Created", False, f"Expected at least 2 updates, got {len(data)}")
                return True
            else:
                self.log_test("Verify System Update Created", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Verify System Update Created", False, f"Error: {str(e)}")
            return False
    
    def test_list_pending_items(self):
        """Test GET /api/pd/requests/{req_id}/pending with status calculation"""
        if not self.internal_research_id:
            self.log_test("List Pending Items", False, "No internal research ID available")
            return False
            
        try:
            # First create a pending item with past date to test status_calc="atrasado"
            past_pending_data = {
                "tipo": "mp",
                "descricao": "Matéria Prima Atrasada",
                "data_prevista": "2024-01-01T00:00:00+00:00",  # Past date
                "fornecedor": "Fornecedor Teste"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/requests/{self.internal_research_id}/pending", json=past_pending_data)
            if response.status_code != 200:
                self.log_test("List Pending Items", False, "Failed to create past pending item")
                return False
            
            # Now list pending items
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/pending")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) >= 2:
                    # Check status_calc logic
                    past_item = next((item for item in data if item.get('descricao') == 'Matéria Prima Atrasada'), None)
                    future_item = next((item for item in data if item.get('descricao') == 'Fragrância Ginger Premium'), None)
                    
                    if (past_item and past_item.get('status_calc') == 'atrasado' and
                        future_item and future_item.get('status_calc') == 'pendente'):
                        self.log_test("List Pending Items", True, f"Found {len(data)} pending items with correct status_calc")
                    else:
                        self.log_test("List Pending Items", False, "status_calc logic not working correctly")
                else:
                    self.log_test("List Pending Items", False, f"Expected at least 2 pending items, got {len(data) if isinstance(data, list) else 'invalid format'}")
                return True
            else:
                self.log_test("List Pending Items", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("List Pending Items", False, f"Error: {str(e)}")
            return False
    
    def test_update_pending_to_received(self):
        """Test PUT /api/pd/pending/{p_id} - mark as received"""
        if not self.pending_id:
            self.log_test("Update Pending to Received", False, "No pending item ID available")
            return False
            
        try:
            update_data = {
                "status": "recebido"
            }
            
            response = self.session.put(f"{BASE_URL}/pd/pending/{self.pending_id}", json=update_data)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('status') == 'recebido' and 
                    data.get('data_recebido') is not None):
                    self.log_test("Update Pending to Received", True, f"Pending item marked as received with timestamp")
                else:
                    self.log_test("Update Pending to Received", False, "Status or timestamp not updated correctly")
                return True
            else:
                self.log_test("Update Pending to Received", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Update Pending to Received", False, f"Error: {str(e)}")
            return False
    
    def test_verify_resolution_update_created(self):
        """Test that marking pending as received auto-created resolution update"""
        if not self.internal_research_id:
            self.log_test("Verify Resolution Update Created", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/updates")
            
            if response.status_code == 200:
                data = response.json()
                # Look for system update about pending resolution
                resolution_update = next((u for u in data if u.get('tipo') == 'pendencia_resolvida'), None)
                if resolution_update and 'Fragrância Ginger' in resolution_update.get('mensagem', ''):
                    self.log_test("Verify Resolution Update Created", True, "System update auto-created for pending resolution")
                else:
                    self.log_test("Verify Resolution Update Created", False, "Resolution update not found or incorrect")
                return True
            else:
                self.log_test("Verify Resolution Update Created", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Verify Resolution Update Created", False, f"Error: {str(e)}")
            return False
    
    def test_delete_pending_item(self):
        """Test DELETE /api/pd/pending/{p_id}"""
        if not self.pending_id:
            self.log_test("Delete Pending Item", False, "No pending item ID available")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/pd/pending/{self.pending_id}")
            
            if response.status_code == 200:
                # Verify item is deleted
                verify_response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/pending")
                if verify_response.status_code == 200:
                    data = verify_response.json()
                    found = any(item.get('id') == self.pending_id for item in data)
                    if not found:
                        self.log_test("Delete Pending Item", True, "Pending item successfully deleted")
                    else:
                        self.log_test("Delete Pending Item", False, "Item still exists after deletion")
                else:
                    self.log_test("Delete Pending Item", False, "Failed to verify deletion")
                return True
            else:
                self.log_test("Delete Pending Item", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Delete Pending Item", False, f"Error: {str(e)}")
            return False
    
    def test_delete_update(self):
        """Test DELETE /api/pd/updates/{up_id}"""
        if not self.update_id:
            self.log_test("Delete Update", False, "No update ID available")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/pd/updates/{self.update_id}")
            
            if response.status_code == 200:
                # Verify update is deleted
                verify_response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/updates")
                if verify_response.status_code == 200:
                    data = verify_response.json()
                    found = any(update.get('id') == self.update_id for update in data)
                    if not found:
                        self.log_test("Delete Update", True, "Update successfully deleted")
                    else:
                        self.log_test("Delete Update", False, "Update still exists after deletion")
                else:
                    self.log_test("Delete Update", False, "Failed to verify deletion")
                return True
            else:
                self.log_test("Delete Update", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Delete Update", False, f"Error: {str(e)}")
            return False
    
    def test_activity_endpoint(self):
        """Test GET /api/pd/requests/{req_id}/activity - CRM-facing view"""
        if not self.internal_research_id:
            self.log_test("Activity Endpoint", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/activity")
            
            if response.status_code == 200:
                data = response.json()
                if 'updates' in data and 'pending' in data:
                    updates = data['updates']
                    pending = data['pending']
                    
                    # Should only show visivel_comercial=true updates
                    all_visible = all(update.get('visivel_comercial') == True for update in updates)
                    
                    if all_visible:
                        self.log_test("Activity Endpoint", True, f"Activity view returned {len(updates)} visible updates and {len(pending)} pending items")
                    else:
                        self.log_test("Activity Endpoint", False, "Some updates are not visible to commercial")
                else:
                    self.log_test("Activity Endpoint", False, "Missing updates or pending keys")
                return True
            else:
                self.log_test("Activity Endpoint", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Activity Endpoint", False, f"Error: {str(e)}")
            return False
    
    def test_full_detail_includes_updates_pending(self):
        """Test GET /api/pd/requests/{req_id}/full includes updates and pending"""
        if not self.internal_research_id:
            self.log_test("Full Detail Includes Updates/Pending", False, "No internal research ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/full")
            
            if response.status_code == 200:
                data = response.json()
                if 'updates' in data and 'pending' in data:
                    updates = data['updates']
                    pending = data['pending']
                    self.log_test("Full Detail Includes Updates/Pending", True, f"Full detail includes {len(updates)} updates and {len(pending)} pending items")
                else:
                    self.log_test("Full Detail Includes Updates/Pending", False, "Missing updates or pending in full detail")
                return True
            else:
                self.log_test("Full Detail Includes Updates/Pending", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Full Detail Includes Updates/Pending", False, f"Error: {str(e)}")
            return False
    
    # ============ 5) INTEGRATION TEST: FORMULA ITEMS WITH CATALOG_ID ============
    
    def test_formula_items_with_catalog_id(self):
        """Test creating formula items with catalog_id field"""
        if not self.internal_research_id:
            self.log_test("Formula Items with Catalog ID", False, "No internal research ID available")
            return False
            
        try:
            # First create a catalog item
            catalog_data = {
                "nome": "Água Destilada",
                "inci": "Aqua",
                "fornecedor": "Lab Supplies",
                "preco_rs_kg": 2.50,
                "categoria": "base"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/catalog", json=catalog_data)
            if response.status_code != 200:
                self.log_test("Formula Items with Catalog ID", False, "Failed to create catalog item")
                return False
            
            catalog_id = response.json().get('id')
            
            # Get development for internal research
            response = self.session.get(f"{BASE_URL}/pd/requests/{self.internal_research_id}/development")
            if response.status_code != 200:
                self.log_test("Formula Items with Catalog ID", False, "Failed to get development")
                return False
            
            dev_id = response.json().get('id')
            
            # Create a formula
            formula_data = {
                "name": "Fórmula Teste com Catalog",
                "volume": 100,
                "volume_unit": "mL"
            }
            
            response = self.session.post(f"{BASE_URL}/pd/developments/{dev_id}/formulas", json=formula_data)
            if response.status_code != 200:
                self.log_test("Formula Items with Catalog ID", False, "Failed to create formula")
                return False
            
            formula_id = response.json().get('id')
            
            # Add formula item with catalog_id
            item_data = {
                "ingredient_name": "Água Destilada",
                "percentage": 80.0,
                "price_per_kg": 2.50,
                "catalog_id": catalog_id
            }
            
            response = self.session.post(f"{BASE_URL}/pd/formulas/{formula_id}/items", json=item_data)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('catalog_id') == catalog_id:
                    self.log_test("Formula Items with Catalog ID", True, f"Formula item created with catalog_id link")
                else:
                    self.log_test("Formula Items with Catalog ID", False, "catalog_id not saved correctly")
                return True
            else:
                self.log_test("Formula Items with Catalog ID", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Formula Items with Catalog ID", False, f"Error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all P&D tests in sequence"""
        print("🚀 Starting P&D Backend Test Suite - New Modules")
        print("=" * 60)
        
        # Authentication
        if not self.login():
            print("❌ Authentication failed. Stopping tests.")
            return False
        
        # Test sequence
        tests = [
            # 1) Cost Catalog Tests
            self.test_create_catalog_item,
            self.test_list_catalog,
            self.test_get_catalog_item,
            self.test_update_catalog_item_price,
            self.test_catalog_price_history,
            self.test_delete_catalog_item,
            
            # 2) Internal Research Tests
            self.test_create_internal_research,
            self.test_verify_pd_card_created,
            self.test_verify_development_created,
            self.test_list_internal_research,
            self.test_verify_pd_cards_includes_pi,
            
            # 3) Lab Stock Tests
            self.test_create_stock_mp_item,
            self.test_create_stock_amostra_acabada,
            self.test_list_stock_with_filter,
            self.test_stock_movement_saida,
            self.test_stock_movement_entrada,
            self.test_stock_movement_invalid_saida,
            self.test_stock_movement_ajuste,
            self.test_list_stock_movements,
            self.test_stock_alerts,
            self.test_update_stock_item,
            self.test_delete_stock_item,
            
            # 4) Updates & Pending Tests
            self.test_create_update,
            self.test_list_updates,
            self.test_create_pending_item,
            self.test_verify_system_update_created,
            self.test_list_pending_items,
            self.test_update_pending_to_received,
            self.test_verify_resolution_update_created,
            self.test_delete_pending_item,
            self.test_delete_update,
            self.test_activity_endpoint,
            self.test_full_detail_includes_updates_pending,
            
            # 5) Integration Test
            self.test_formula_items_with_catalog_id
        ]
        
        for test in tests:
            test()
            print()  # Add spacing between tests
        
        # Summary
        print("=" * 60)
        print("📊 P&D TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if total - passed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        return passed == total

if __name__ == "__main__":
    tester = PDTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)