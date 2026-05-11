#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen Coder AI Integration Module
Integracja z coder.qwen.ai - automatyczne logowanie i wysyłanie zapytań

Funkcje:
    - Logowanie do coder.qwen.ai przy użyciu danych z pliku konfiguracyjnego
    - Wysyłanie zapytań do modelu Qwen Coder
    - Odbieranie i parsowanie odpowiedzi
    - Obsługa sesji przeglądarkowej przez Selenium/Playwright
    - Integracja z klastrem Raspberry Pi (3x RPi4 + 3x RPi1)
    
Autor: bartosz.ruta26@gmail.com
Licencja: MIT
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# KONFIGURACJA
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.absolute()
CONFIG_FILE = SCRIPT_DIR / "config.json"
SESSIONS_DIR = SCRIPT_DIR / "qwen_sessions"
LOGS_DIR = SCRIPT_DIR / "logs"

# Domyślne ustawienia klastra
CLUSTER_CONFIG = {
    "nodes": [
        {"id": "rpi4-1", "type": "rpi4", "host": "192.168.1.101", "port": 8080, "cores": 4},
        {"id": "rpi4-2", "type": "rpi4", "host": "192.168.1.102", "port": 8080, "cores": 4},
        {"id": "rpi4-3", "type": "rpi4", "host": "192.168.1.103", "port": 8080, "cores": 4},
        {"id": "rpi1-1", "type": "rpi1", "host": "192.168.1.104", "port": 8080, "cores": 1},
        {"id": "rpi1-2", "type": "rpi1", "host": "192.168.1.105", "port": 8080, "cores": 1},
        {"id": "rpi1-3", "type": "rpi1", "host": "192.168.1.106", "port": 8080, "cores": 1},
    ],
    "mode": "serial",  # serial, parallel, hybrid
    "current_node": 0
}


# ============================================================================
# KLASA QWEN_CODER_INTEGRATION
# ============================================================================

class QwenCoderIntegration:
    """
    Klasa obsługująca integrację z coder.qwen.ai
    
    Wymagania:
        - selenium lub playwright do automatyzacji przeglądarki
        - plik konfiguracyjny z danymi logowania
        - aktywne połączenie internetowe
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Inicjalizacja integracji
        
        Args:
            config_path: Ścieżka do pliku konfiguracyjnego (domyślnie config.json)
        """
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()
        self.session = None
        self.browser = None
        self.is_logged_in = False
        self.current_task_id = None
        
        # Zapewnij istnienie katalogów
        SESSIONS_DIR.mkdir(exist_ok=True)
        LOGS_DIR.mkdir(exist_ok=True)
        
        logger.info("Zainicjalizowano QwenCoderIntegration")
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Ładuje konfigurację z pliku JSON
        
        Returns:
            Słownik z konfiguracją
        """
        if not self.config_path.exists():
            logger.warning(f"Plik konfiguracyjny nie istnieje: {self.config_path}")
            return self._create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Załadowano konfigurację z {self.config_path}")
                return config
        except Exception as e:
            logger.error(f"Błąd ładowania konfiguracji: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """
        Tworzy domyślną konfigurację
        
        Returns:
            Słownik z domyślną konfiguracją
        """
        default_config = {
            "qwen_coder": {
                "email": "bartosz.ruta26@gmail.com",
                "password": "",  # Ustaw w pliku konfiguracyjnym
                "base_url": "https://coder.qwen.ai",
                "login_url": "https://coder.qwen.ai/login",
                "api_endpoint": "https://coder.qwen.ai/api/v1/chat/completions"
            },
            "cluster": CLUSTER_CONFIG,
            "browser": {
                "headless": False,
                "timeout": 60,
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            },
            "processing": {
                "max_retries": 3,
                "retry_delay": 5,
                "task_timeout": 300
            }
        }
        
        # Zapisz domyślną konfigurację
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Utworzono domyślny plik konfiguracyjny: {self.config_path}")
        except Exception as e:
            logger.error(f"Błąd zapisu domyślnej konfiguracji: {e}")
        
        return default_config
    
    def initialize_browser(self, browser_type: str = "selenium") -> bool:
        """
        Inicjalizuje przeglądarkę do automatyzacji
        
        Args:
            browser_type: Typ przeglądarki ("selenium" lub "playwright")
            
        Returns:
            True jeśli inicjalizacja powiodła się
        """
        try:
            if browser_type == "selenium":
                return self._init_selenium()
            elif browser_type == "playwright":
                return self._init_playwright()
            else:
                logger.error(f"Nieznany typ przeglądarki: {browser_type}")
                return False
        except Exception as e:
            logger.error(f"Błąd inicjalizacji przeglądarki: {e}")
            return False
    
    def _init_selenium(self) -> bool:
        """
        Inicjalizuje Selenium WebDriver
        
        Returns:
            True jeśli inicjalizacja powiodła się
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from webdriver_manager.chrome import ChromeDriverManager
            
            chrome_options = Options()
            
            if self.config.get("browser", {}).get("headless", False):
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            user_agent = self.config.get("browser", {}).get("user_agent", "")
            if user_agent:
                chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # Użyj webdriver-manager do automatycznego pobrania ChromeDriver
            try:
                service = Service(ChromeDriverManager().install())
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
            except Exception:
                # Fallback: spróbuj użyć chromedriver z systemu
                try:
                    self.browser = webdriver.Chrome(options=chrome_options)
                except Exception:
                    logger.warning("ChromeDriver nieznaleziony, próba użycia Chromium")
                    chrome_options.binary_location = "/usr/bin/chromium"
                    self.browser = webdriver.Chrome(options=chrome_options)
            
            self.browser.set_page_load_timeout(
                self.config.get("browser", {}).get("timeout", 60)
            )
            
            logger.info("Zainicjalizowano Selenium WebDriver")
            return True
            
        except ImportError as e:
            logger.error(f"Błąd importu: {e}. Uruchom: pip install selenium webdriver-manager")
            return False
        except Exception as e:
            logger.error(f"Błąd inicjalizacji Selenium: {e}")
            logger.info("Sprawdź czy Chrome/Chromium i ChromeDriver są zainstalowane")
            return False
    
    def _init_playwright(self) -> bool:
        """
        Inicjalizuje Playwright
        
        Returns:
            True jeśli inicjalizacja powiodła się
        """
        try:
            from playwright.sync_api import sync_playwright
            
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get("browser", {}).get("headless", False)
            )
            
            logger.info("Zainicjalizowano Playwright")
            return True
            
        except ImportError:
            logger.error("Playwright nie jest zainstalowane. Uruchom: pip install playwright")
            return False
        except Exception as e:
            logger.error(f"Błąd inicjalizacji Playwright: {e}")
            return False
    
    def login(self) -> bool:
        """
        Loguje się do coder.qwen.ai
        
        Returns:
            True jeśli logowanie powiodło się
        """
        qwen_config = self.config.get("qwen_coder", {})
        email = qwen_config.get("email", "")
        password = qwen_config.get("password", "")
        login_url = qwen_config.get("login_url", "https://coder.qwen.ai/login")
        
        if not email or not password:
            logger.error("Brak danych logowania w konfiguracji")
            return False
        
        if not self.browser:
            logger.error("Przeglądarka nie jest zainicjalizowana")
            return False
        
        try:
            logger.info(f"Logowanie do {login_url} jako {email}")
            
            if hasattr(self, 'playwright'):
                # Playwright
                page = self.browser.new_page()
                page.goto(login_url)
                
                # Znajdź pola logowania i wypełnij je
                page.fill('input[type="email"]', email)
                page.fill('input[type="password"]', password)
                page.click('button[type="submit"]')
                
                # Poczekaj na przekierowanie
                page.wait_for_url("https://coder.qwen.ai/**", timeout=30000)
                
            else:
                # Selenium
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                self.browser.get(login_url)
                
                wait = WebDriverWait(self.browser, 30)
                
                # Wypełnij formularz logowania
                email_field = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'input[type="email"]')
                ))
                email_field.clear()
                email_field.send_keys(email)
                
                password_field = self.browser.find_element(
                    By.CSS_SELECTOR, 'input[type="password"]'
                )
                password_field.clear()
                password_field.send_keys(password)
                
                # Wyślij formularz
                submit_button = self.browser.find_element(
                    By.CSS_SELECTOR, 'button[type="submit"]'
                )
                submit_button.click()
                
                # Poczekaj na przekierowanie
                wait.until(lambda driver: "coder.qwen.ai" in driver.current_url)
            
            self.is_logged_in = True
            logger.info("Logowanie zakończone sukcesem")
            
            # Zapisz sesję
            self._save_session()
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd logowania: {e}")
            return False
    
    def _save_session(self):
        """Zapisuje stan sesji do pliku"""
        session_data = {
            "timestamp": datetime.now().isoformat(),
            "is_logged_in": self.is_logged_in,
            "email": self.config.get("qwen_coder", {}).get("email", "")
        }
        
        session_file = SESSIONS_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
            logger.info(f"Zapisano sesję do {session_file}")
        except Exception as e:
            logger.error(f"Błąd zapisu sesji: {e}")
    
    def send_query(self, query: str, context: Optional[Dict] = None) -> Optional[str]:
        """
        Wysyła zapytanie do coder.qwen.ai i czeka na odpowiedź
        
        Args:
            query: Treść zapytania
            context: Dodatkowy kontekst (opcjonalnie)
            
        Returns:
            Odpowiedź z modelu lub None w przypadku błędu
        """
        if not self.is_logged_in:
            logger.error("Nie zalogowano. Wywołaj login() najpierw.")
            return None
        
        if not self.browser:
            logger.error("Przeglądarka nie jest zainicjalizowana")
            return None
        
        try:
            base_url = self.config.get("qwen_coder", {}).get("base_url", "https://coder.qwen.ai")
            
            logger.info(f"Wysyłanie zapytania: {query[:100]}...")
            
            if hasattr(self, 'playwright'):
                # Playwright
                page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()
                page.goto(f"{base_url}/chat")
                
                # Znajdź pole input i wyślij zapytanie
                page.wait_for_selector('textarea[placeholder*="Message"]', timeout=10000)
                page.fill('textarea[placeholder*="Message"]', query)
                page.press('textarea[placeholder*="Message"]', 'Enter')
                
                # Poczekaj na odpowiedź
                logger.info("Oczekiwanie na odpowiedź...")
                response = self._wait_for_response_playwright(page)
                
            else:
                # Selenium
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                self.browser.get(f"{base_url}/chat")
                
                wait = WebDriverWait(self.browser, 30)
                
                # Znajdź pole input
                input_field = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'textarea[placeholder*="Message"]')
                ))
                input_field.clear()
                input_field.send_keys(query)
                
                # Wyślij zapytanie
                input_field.send_keys(u'\ue007')  # Enter key
                
                # Poczekaj na odpowiedź
                logger.info("Oczekiwanie na odpowiedź...")
                response = self._wait_for_response_selenium(wait)
            
            if response:
                logger.info(f"Otrzymano odpowiedź ({len(response)} znaków)")
                self._log_query_response(query, response)
                return response
            else:
                logger.warning("Nie otrzymano odpowiedzi")
                return None
                
        except Exception as e:
            logger.error(f"Błąd wysyłania zapytania: {e}")
            return None
    
    def _wait_for_response_selenium(self, wait) -> Optional[str]:
        """
        Czeka na odpowiedź w Selenium
        
        Args:
            wait: WebDriverWait object
            
        Returns:
            Treść odpowiedzi lub None
        """
        try:
            # Poczekaj aż pojawi się odpowiedź
            response_element = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '.message.assistant, .response, [data-role="assistant"]')
                ),
                timeout=60
            )
            
            # Pobierz treść odpowiedzi
            response_text = response_element.text
            return response_text if response_text else None
            
        except Exception as e:
            logger.error(f"Timeout oczekiwania na odpowiedź: {e}")
            return None
    
    def _wait_for_response_playwright(self, page) -> Optional[str]:
        """
        Czeka na odpowiedź w Playwright
        
        Args:
            page: Page object
            
        Returns:
            Treść odpowiedzi lub None
        """
        try:
            # Poczekaj na element odpowiedzi
            page.wait_for_selector('.message.assistant, .response, [data-role="assistant"]', timeout=60000)
            
            # Pobierz treść
            response_elements = page.query_selector_all('.message.assistant, .response, [data-role="assistant"]')
            if response_elements:
                return response_elements[-1].inner_text()
            
            return None
            
        except Exception as e:
            logger.error(f"Timeout oczekiwania na odpowiedź: {e}")
            return None
    
    def _log_query_response(self, query: str, response: str):
        """Loguje zapytanie i odpowiedź do pliku"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": response,
            "query_length": len(query),
            "response_length": len(response)
        }
        
        log_file = LOGS_DIR / f"qwen_queries_{datetime.now().strftime('%Y%m%d')}.jsonl"
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Błąd zapisu logu: {e}")
    
    def process_batch_sequential(self, queries: List[str], node_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Przetwarza wiele zapytań szeregowo na dostępnych node'ach
        
        Args:
            queries: Lista zapytań do przetworzenia
            node_ids: Lista ID node'ów do użycia (domyślnie wszystkie)
            
        Returns:
            Lista wyników
        """
        cluster_config = self.config.get("cluster", CLUSTER_CONFIG)
        nodes = cluster_config.get("nodes", [])
        
        if node_ids:
            nodes = [n for n in nodes if n["id"] in node_ids]
        
        if not nodes:
            logger.error("Brak dostępnych node'ów")
            return []
        
        results = []
        node_index = 0
        
        logger.info(f"Rozpoczynanie przetwarzania szeregowego {len(queries)} zapytań na {len(nodes)} node'ach")
        
        for i, query in enumerate(queries):
            # Wybierz node w trybie round-robin
            current_node = nodes[node_index % len(nodes)]
            node_index += 1
            
            logger.info(f"[{i+1}/{len(queries)}] Przetwarzanie na node: {current_node['id']}")
            
            result = {
                "query_index": i,
                "node_id": current_node["id"],
                "node_type": current_node["type"],
                "query": query,
                "response": None,
                "success": False,
                "error": None,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                response = self.send_query(query)
                if response:
                    result["response"] = response
                    result["success"] = True
                else:
                    result["error"] = "Brak odpowiedzi"
            except Exception as e:
                result["error"] = str(e)
            
            results.append(result)
            
            # Małe opóźnienie między zapytaniami
            time.sleep(1)
        
        logger.info(f"Zakończono przetwarzanie szeregowe. Sukcesów: {sum(1 for r in results if r['success'])}/{len(results)}")
        return results
    
    def close(self):
        """Zamyka połączenie z przeglądarką"""
        if self.browser:
            try:
                if hasattr(self, 'playwright'):
                    self.browser.close()
                    self.playwright.stop()
                else:
                    self.browser.quit()
                logger.info("Zamknięto przeglądarkę")
            except Exception as e:
                logger.error(f"Błąd zamykania przeglądarki: {e}")
        
        self.is_logged_in = False


# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

def create_cluster_task(query: str, priority: int = 5, target_node: Optional[str] = None) -> Dict:
    """
    Tworzy zadanie dla klastra
    
    Args:
        query: Zapytanie do przetworzenia
        priority: Priorytet (1-10)
        target_node: Docelowy node (opcjonalnie)
    
    Returns:
        Słownik z danymi zadania
    """
    import uuid
    return {
        "id": str(uuid.uuid4())[:8],
        "type": "qwen_query",
        "query": query,
        "priority": priority,
        "target_node": target_node,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }


def run_sequential_pipeline(queries: List[str], config_path: Optional[Path] = None):
    """
    Uruchamia szeregowe przetwarzanie zapytań na klastrze
    
    Args:
        queries: Lista zapytań
        config_path: Ścieżka do konfiguracji
    """
    logger.info("=" * 60)
    logger.info("🚀 Qwen Coder AI - Szeregowe Przetwarzanie Klastra")
    logger.info("=" * 60)
    
    integrator = QwenCoderIntegration(config_path)
    
    try:
        # Inicjalizacja przeglądarki
        logger.info("Inicjalizacja przeglądarki...")
        if not integrator.initialize_browser("selenium"):
            logger.error("Nie udało się zainicjalizować przeglądarki")
            return
        
        # Logowanie
        logger.info("Logowanie do coder.qwen.ai...")
        if not integrator.login():
            logger.error("Nie udało się zalogować")
            return
        
        # Przetwarzanie szeregowe
        logger.info(f"Przetwarzanie {len(queries)} zapytań...")
        results = integrator.process_batch_sequential(queries)
        
        # Podsumowanie
        success_count = sum(1 for r in results if r["success"])
        logger.info("=" * 60)
        logger.info(f"✅ Zakończono: {success_count}/{len(results)} zapytań")
        logger.info("=" * 60)
        
        # Zapisz wyniki
        output_file = LOGS_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Zapisano wyniki do {output_file}")
        
    finally:
        integrator.close()


# ============================================================================
# GŁÓWNA FUNKCJA
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Qwen Coder AI Integration')
    parser.add_argument('--config', type=str, help='Ścieżka do pliku konfiguracyjnego')
    parser.add_argument('--test', action='store_true', help='Uruchom test logowania')
    parser.add_argument('--query', type=str, help='Pojedyncze zapytanie do wysłania')
    parser.add_argument('--batch', type=str, help='Plik JSON z listą zapytań')
    
    args = parser.parse_args()
    
    config_path = Path(args.config) if args.config else None
    integrator = QwenCoderIntegration(config_path)
    
    try:
        if args.test:
            # Test logowania
            print("Test logowania do coder.qwen.ai...")
            if integrator.initialize_browser("selenium"):
                if integrator.login():
                    print("✅ Logowanie zakończone sukcesem!")
                else:
                    print("❌ Logowanie nieudane")
            else:
                print("❌ Nie udało się zainicjalizować przeglądarki")
        
        elif args.query:
            # Pojedyncze zapytanie
            if integrator.initialize_browser("selenium") and integrator.login():
                response = integrator.send_query(args.query)
                if response:
                    print("\n" + "=" * 60)
                    print("ODPOWIEDŹ:")
                    print("=" * 60)
                    print(response)
                    print("=" * 60)
                else:
                    print("❌ Nie otrzymano odpowiedzi")
        
        elif args.batch:
            # Batch zapytań z pliku
            batch_file = Path(args.batch)
            if batch_file.exists():
                with open(batch_file, 'r', encoding='utf-8') as f:
                    queries = json.load(f)
                
                if isinstance(queries, list):
                    run_sequential_pipeline(queries, config_path)
                else:
                    print("❌ Plik batch powinien zawierać listę zapytań")
            else:
                print(f"❌ Plik nie istnieje: {batch_file}")
        
        else:
            parser.print_help()
    
    finally:
        integrator.close()
