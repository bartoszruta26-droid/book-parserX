#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen Coder AI Integration Module - Wersja dla klastra Raspberry Pi z pełną integracją Moodle
Integracja z wieloma platformami AI: coder.qwen.ai, chatgpt.com, grok.com

Funkcje:
    - Logowanie do wielu platform AI przy użyciu danych z pliku konfiguracyjnego
    - Wysyłanie zapytań do różnych modeli AI (Qwen Coder, ChatGPT, Grok)
    - Odbieranie i parsowanie odpowiedzi
    - Obsługa sesji przeglądarkowej przez Selenium/Playwright
    - Integracja z klastrem Raspberry Pi (3x RPi4 + 3x RPi1)
    - WSZYSTKIE RPi (4 i 1) korzystają z webowych AI
    - Master RPi zbiera odpowiedzi ze wszystkich node'ów
    - Master wysyła zebrane odpowiedzi do LLM Qwen w celu połączenia
    - Połączony tekst jest wysyłany do Moodle course activity
    
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
from enum import Enum

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
RESULTS_DIR = SCRIPT_DIR / "results"


class NodeType(Enum):
    """Typy node'ów w klastrze"""
    RPI4 = "rpi4"  # Wykorzystuje webowe AI (jak RPi1)
    RPI1 = "rpi1"  # Wykorzystuje webowe AI


class AIPlatform(Enum):
    """Dostępne platformy AI - wszystkie webowe"""
    QWEN_CODER = "coder.qwen.ai"
    CHATGPT = "chatgpt.com"
    GROK = "grok.com"
    QWEN_LLM = "llm.qwen.ai"  # Dodatkowa platforma Qwen dla mastera


# Domyślne ustawienia klastra - WSZYSTKIE node'y używają webowych AI
CLUSTER_CONFIG = {
    "nodes": [
        # Master node - RPi4 z Qwen LLM do łączenia tekstów
        {"id": "rpi4-1", "type": "rpi4", "host": "192.168.1.101", "port": 8080, "cores": 4, 
         "ai_platform": "llm.qwen.ai", "credentials_profile": "qwen_master_profile", "role": "master"},
        # Worker nodes - RPi4 z różnymi platformami AI
        {"id": "rpi4-2", "type": "rpi4", "host": "192.168.1.102", "port": 8080, "cores": 4,
         "ai_platform": "coder.qwen.ai", "credentials_profile": "qwen_profile_1", "role": "worker"},
        {"id": "rpi4-3", "type": "rpi4", "host": "192.168.1.103", "port": 8080, "cores": 4,
         "ai_platform": "chatgpt.com", "credentials_profile": "chatgpt_profile_1", "role": "worker"},
        # Worker nodes - RPi1 z różnymi platformami AI
        {"id": "rpi1-1", "type": "rpi1", "host": "192.168.1.104", "port": 8080, "cores": 1,
         "ai_platform": "coder.qwen.ai", "credentials_profile": "qwen_profile_2", "role": "worker"},
        {"id": "rpi1-2", "type": "rpi1", "host": "192.168.1.105", "port": 8080, "cores": 1,
         "ai_platform": "chatgpt.com", "credentials_profile": "chatgpt_profile_2", "role": "worker"},
        {"id": "rpi1-3", "type": "rpi1", "host": "192.168.1.106", "port": 8080, "cores": 1,
         "ai_platform": "grok.com", "credentials_profile": "grok_profile_1", "role": "worker"},
    ],
    "mode": "serial",  # serial, parallel, hybrid
    "current_node": 0,
    "master_node": "rpi4-1"
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
        Tworzy domyślną konfigurację z obsługą wielu platform AI i profili logowania
        
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
            "chatgpt": {
                "email": "",
                "password": "",
                "base_url": "https://chatgpt.com",
                "login_url": "https://chatgpt.com/auth/login"
            },
            "grok": {
                "email": "",
                "password": "",
                "base_url": "https://grok.com",
                "login_url": "https://grok.com/login"
            },
            # Profile logowania dla różnych node'ów - każdy może mieć inne dane
            "credentials_profiles": {
                "qwen_master_profile": {
                    "platform": "llm.qwen.ai",
                    "email": "bartosz.ruta26@gmail.com",
                    "password": ""
                },
                "qwen_profile_1": {
                    "platform": "coder.qwen.ai",
                    "email": "user1@example.com",
                    "password": ""
                },
                "qwen_profile_2": {
                    "platform": "coder.qwen.ai",
                    "email": "user2@example.com",
                    "password": ""
                },
                "chatgpt_profile_1": {
                    "platform": "chatgpt.com",
                    "email": "chatgpt_user1@example.com",
                    "password": ""
                },
                "chatgpt_profile_2": {
                    "platform": "chatgpt.com",
                    "email": "chatgpt_user2@example.com",
                    "password": ""
                },
                "grok_profile_1": {
                    "platform": "grok.com",
                    "email": "grok_user1@example.com",
                    "password": ""
                },
                "grok_profile_2": {
                    "platform": "grok.com",
                    "email": "grok_user2@example.com",
                    "password": ""
                }
            },
            "qwen_llm": {
                "enabled": True,
                "base_url": "https://llm.qwen.ai",
                "login_url": "https://llm.qwen.ai/login",
                "api_endpoint": "https://llm.qwen.ai/api/v1/chat/completions"
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
                "task_timeout": 300,
                "aggregation_enabled": True
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
    
    def login(self, platform: Optional[str] = None) -> bool:
        """
        Loguje się do platformy AI (coder.qwen.ai, chatgpt.com, grok.com)
        
        Args:
            platform: Nazwa platformy (domyślnie z konfiguracji qwen_coder.platform)
        
        Returns:
            True jeśli logowanie powiodło się
        """
        # Sprawdź czy mamy konfigurację dla konkretnej platformy
        if platform:
            platform_key = platform.replace(".", "_").replace("-", "_")
            platform_config = self.config.get(platform_key, {})
            email = platform_config.get("email", "")
            password = platform_config.get("password", "")
            login_url = platform_config.get("login_url", "")
            base_url = platform_config.get("base_url", f"https://{platform}")
        else:
            qwen_config = self.config.get("qwen_coder", {})
            email = qwen_config.get("email", "")
            password = qwen_config.get("password", "")
            login_url = qwen_config.get("login_url", "https://coder.qwen.ai/login")
            base_url = qwen_config.get("base_url", "https://coder.qwen.ai")
            platform = "coder.qwen.ai"
        
        if not email or not password:
            logger.error("Brak danych logowania w konfiguracji")
            return False
        
        if not self.browser:
            logger.error("Przeglądarka nie jest zainicjalizowana")
            return False
        
        try:
            logger.info(f"Logowanie do {login_url} jako {email} (platforma: {platform})")
            
            if hasattr(self, 'playwright'):
                # Playwright
                page = self.browser.new_page()
                page.goto(login_url)
                
                # Znajdź pola logowania i wypełnij je - różne selektory dla różnych platform
                if "chatgpt" in platform:
                    page.fill('input[type="email"]', email)
                    page.fill('input[type="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_url("https://chatgpt.com/**", timeout=30000)
                elif "grok" in platform:
                    page.fill('input[type="email"]', email)
                    page.fill('input[type="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_url("https://grok.com/**", timeout=30000)
                else:
                    # Domyślnie dla qwen
                    page.fill('input[type="email"]', email)
                    page.fill('input[type="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_url("https://coder.qwen.ai/**", timeout=30000)
                
            else:
                # Selenium
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                self.browser.get(login_url)
                
                wait = WebDriverWait(self.browser, 30)
                
                # Wypełnij formularz logowania - różne selektory dla różnych platform
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
                
                # Poczekaj na przekierowanie - różne URL dla różnych platform
                if "chatgpt" in platform:
                    wait.until(lambda driver: "chatgpt.com" in driver.current_url)
                elif "grok" in platform:
                    wait.until(lambda driver: "grok.com" in driver.current_url)
                else:
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
    
    def send_query(self, query: str, context: Optional[Dict] = None, platform: Optional[str] = None) -> Optional[str]:
        """
        Wysyła zapytanie do platformy AI i czeka na odpowiedź
        
        Args:
            query: Treść zapytania
            context: Dodatkowy kontekst (opcjonalnie)
            platform: Nazwa platformy (domyślnie z konfiguracji)
            
        Returns:
            Odpowiedź z modelu lub None w przypadku błędu
        """
        if not self.is_logged_in:
            logger.error("Nie zalogowano. Wywołaj login() najpierw.")
            return None
        
        if not self.browser:
            logger.error("Przeglądarka nie jest zainicjalizowana")
            return None
        
        # Określ platformę i base_url
        if platform:
            platform_key = platform.replace(".", "_").replace("-", "_")
            platform_config = self.config.get(platform_key, {})
            base_url = platform_config.get("base_url", f"https://{platform}")
        else:
            base_url = self.config.get("qwen_coder", {}).get("base_url", "https://coder.qwen.ai")
            platform = "coder.qwen.ai"
        
        try:
            logger.info(f"Wysyłanie zapytania do {platform}: {query[:100]}...")
            
            if hasattr(self, 'playwright'):
                # Playwright
                page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()
                page.goto(f"{base_url}/chat")
                
                # Znajdź pole input i wyślij zapytanie - różne selektory dla różnych platform
                if "chatgpt" in platform:
                    page.wait_for_selector('textarea[placeholder*="Message"]', timeout=10000)
                    page.fill('textarea[placeholder*="Message"]', query)
                    page.press('textarea[placeholder*="Message"]', 'Enter')
                elif "grok" in platform:
                    page.wait_for_selector('textarea, [contenteditable]', timeout=10000)
                    page.fill('textarea, [contenteditable]', query)
                    page.press('textarea, [contenteditable]', 'Enter')
                else:
                    # Domyślnie dla qwen
                    page.wait_for_selector('textarea[placeholder*="Message"]', timeout=10000)
                    page.fill('textarea[placeholder*="Message"]', query)
                    page.press('textarea[placeholder*="Message"]', 'Enter')
                
                # Poczekaj na odpowiedź
                logger.info("Oczekiwanie na odpowiedź...")
                response = self._wait_for_response_playwright(page, platform)
                
            else:
                # Selenium
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                self.browser.get(f"{base_url}/chat")
                
                wait = WebDriverWait(self.browser, 30)
                
                # Znajdź pole input - różne selektory dla różnych platform
                if "chatgpt" in platform:
                    input_field = wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'textarea[placeholder*="Message"]')
                    ))
                elif "grok" in platform:
                    input_field = wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'textarea, [contenteditable]')
                    ))
                else:
                    input_field = wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'textarea[placeholder*="Message"]')
                    ))
                
                input_field.clear()
                input_field.send_keys(query)
                
                # Wyślij zapytanie
                input_field.send_keys(u'\ue007')  # Enter key
                
                # Poczekaj na odpowiedź
                logger.info("Oczekiwanie na odpowiedź...")
                response = self._wait_for_response_selenium(wait, platform)
            
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
    
    def _wait_for_response_selenium(self, wait, platform: Optional[str] = None) -> Optional[str]:
        """
        Czeka na odpowiedź w Selenium
        
        Args:
            wait: WebDriverWait object
            platform: Nazwa platformy (dla różnych selektorów)
            
        Returns:
            Treść odpowiedzi lub None
        """
        try:
            # Różne selektory dla różnych platform
            if platform and "chatgpt" in platform:
                selectors = '.message.assistant, .response, [data-role="assistant"], article.markdown'
            elif platform and "grok" in platform:
                selectors = '.message.assistant, .response, [data-role="assistant"], .prose'
            else:
                selectors = '.message.assistant, .response, [data-role="assistant"]'
            
            # Poczekaj aż pojawi się odpowiedź
            response_element = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, selectors)
                ),
                timeout=60
            )
            
            # Pobierz treść odpowiedzi
            response_text = response_element.text
            return response_text if response_text else None
            
        except Exception as e:
            logger.error(f"Timeout oczekiwania na odpowiedź: {e}")
            return None
    
    def _wait_for_response_playwright(self, page, platform: Optional[str] = None) -> Optional[str]:
        """
        Czeka na odpowiedź w Playwright
        
        Args:
            page: Page object
            platform: Nazwa platformy (dla różnych selektorów)
            
        Returns:
            Treść odpowiedzi lub None
        """
        try:
            # Różne selektory dla różnych platform
            if platform and "chatgpt" in platform:
                selector = '.message.assistant, .response, [data-role="assistant"], article.markdown'
            elif platform and "grok" in platform:
                selector = '.message.assistant, .response, [data-role="assistant"], .prose'
            else:
                selector = '.message.assistant, .response, [data-role="assistant"]'
            
            # Poczekaj na element odpowiedzi
            page.wait_for_selector(selector, timeout=60000)
            
            # Pobierz treść
            response_elements = page.query_selector_all(selector)
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
                # Pobierz platformę dla tego node'a
                ai_platform = current_node.get("ai_platform", "coder.qwen.ai")
                response = self.send_query(query, platform=ai_platform)
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
# KLASA MULTI_AI_INTEGRATION - Obsługa wielu platform AI
# ============================================================================

class MultiAIIntegration:
    """
    Klasa obsługująca integrację z wieloma platformami AI:
    - coder.qwen.ai
    - chatgpt.com
    - grok.com
    - Local LLM (dla RPi4)
    
    Każdy node klastra może używać innych danych logowania do różnych platform.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Inicjalizacja integracji z wieloma AI
        
        Args:
            config_path: Ścieżka do pliku konfiguracyjnego
        """
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()
        self.sessions: Dict[str, QwenCoderIntegration] = {}
        self.browser_sessions: Dict[str, Any] = {}
        
        # Zapewnij istnienie katalogów
        RESULTS_DIR.mkdir(exist_ok=True)
        
        logger.info("Zainicjalizowano MultiAIIntegration")
    
    def _load_config(self) -> Dict[str, Any]:
        """Ładuje konfigurację"""
        if not self.config_path.exists():
            logger.warning(f"Plik konfiguracyjny nie istnieje: {self.config_path}")
            return {}
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Błąd ładowania konfiguracji: {e}")
            return {}
    
    def get_credentials_for_node(self, node_id: str) -> Dict[str, str]:
        """
        Pobiera dane logowania dla konkretnego node'a
        
        Args:
            node_id: ID node'a
            
        Returns:
            Słownik z danymi logowania (email, password, platform)
        """
        cluster_config = self.config.get("cluster", {})
        nodes = cluster_config.get("nodes", [])
        
        node = next((n for n in nodes if n["id"] == node_id), None)
        if not node:
            logger.error(f"Nie znaleziono node'a: {node_id}")
            return {}
        
        ai_platform = node.get("ai_platform", "coder.qwen.ai")
        credentials_profile = node.get("credentials_profile", "")
        
        if credentials_profile and credentials_profile in self.config.get("credentials_profiles", {}):
            profile = self.config["credentials_profiles"][credentials_profile]
            return {
                "email": profile.get("email", ""),
                "password": profile.get("password", ""),
                "platform": profile.get("platform", ai_platform),
                "login_url": self._get_login_url(profile.get("platform", ai_platform))
            }
        
        # Fallback do domyślnej konfiguracji platformy
        platform_config = self.config.get(ai_platform.replace(".", "_").replace("-", "_"), {})
        return {
            "email": platform_config.get("email", ""),
            "password": platform_config.get("password", ""),
            "platform": ai_platform,
            "login_url": platform_config.get("login_url", "")
        }
    
    def _get_login_url(self, platform: str) -> str:
        """Pobiera URL logowania dla platformy"""
        urls = {
            "coder.qwen.ai": "https://coder.qwen.ai/login",
            "chatgpt.com": "https://chatgpt.com/auth/login",
            "grok.com": "https://grok.com/login",
            "llm.qwen.ai": "https://llm.qwen.ai/login"
        }
        return urls.get(platform, "")
    
    def login_to_platform(self, node_id: str, browser_type: str = "selenium") -> bool:
        """
        Loguje się do platformy AI przypisanej do node'a
        
        Args:
            node_id: ID node'a
            browser_type: Typ przeglądarki
            
        Returns:
            True jeśli logowanie powiodło się
        """
        credentials = self.get_credentials_for_node(node_id)
        if not credentials.get("email") or not credentials.get("password"):
            logger.error(f"Brak danych logowania dla node'a {node_id}")
            return False
        
        # Utwórz nową sesję dla tego node'a
        session = QwenCoderIntegration(self.config_path)
        
        if not session.initialize_browser(browser_type):
            logger.error(f"Nie udało się zainicjalizować przeglądarki dla {node_id}")
            return False
        
        # Platforma dla tego node'a
        platform = credentials['platform']
        
        # Zaktualizuj konfigurację sesji dla konkretnej platformy
        platform_key = platform.replace(".", "_").replace("-", "_")
        if platform_key not in session.config:
            session.config[platform_key] = {}
        session.config[platform_key]["email"] = credentials["email"]
        session.config[platform_key]["password"] = credentials["password"]
        
        # Logowanie z platformą
        if not session.login(platform=platform):
            session.close()
            return False
        
        self.sessions[node_id] = session
        logger.info(f"Zalogowano node {node_id} do {credentials['platform']}")
        return True
    
    def send_query_to_node(self, node_id: str, query: str) -> Optional[str]:
        """
        Wysyła zapytanie do konkretnego node'a
        
        Args:
            node_id: ID node'a
            query: Treść zapytania
            
        Returns:
            Odpowiedź z AI lub None
        """
        cluster_config = self.config.get("cluster", {})
        nodes = cluster_config.get("nodes", [])
        
        node = next((n for n in nodes if n["id"] == node_id), None)
        if not node:
            logger.error(f"Nie znaleziono node'a: {node_id}")
            return None
        
        ai_platform = node.get("ai_platform", "coder.qwen.ai")
        
        # Wszystkie node'y używają webowych AI - brak lokalnego LLM
        if node_id not in self.sessions:
            logger.error(f"Node {node_id} nie jest zalogowany")
            return None
        
        session = self.sessions[node_id]
        return session.send_query(query)
    
    def _query_local_llm(self, node_id: str, query: str, node_config: Dict) -> Optional[str]:
        """
        Wysyła zapytanie do Qwen LLM przez stronę webową (dla mastera)
        
        Args:
            node_id: ID node'a
            query: Treść zapytania
            node_config: Konfiguracja node'a
            
        Returns:
            Odpowiedź z LLM lub None
        """
        # Ta metoda jest przestarzała - wszystkie node'y używają webowych AI
        logger.warning(f"_query_local_llm jest przestarzała - użyj send_query_to_node")
        return self.send_query_to_node(node_id, query)
    
    def merge_texts_with_qwen(self, collected_texts: List[str], chunk_metadata: Dict = None) -> Optional[str]:
        """
        Wysyła zebrane teksty do Qwen LLM w celu połączenia w jeden spójny tekst
        
        Args:
            collected_texts: Lista tekstów zebranych z różnych AI
            chunk_metadata: Metadane o chunkach (opcjonalnie)
            
        Returns:
            Połączony tekst lub None
        """
        master_node = self.config.get("cluster", {}).get("master_node", "rpi4-1")
        
        # Przygotuj prompt do łączenia tekstów
        merge_prompt = f"""Jesteś asystentem do łączenia tekstów. Masz za zadanie połączyć poniższe fragmenty tekstu 
w jeden spójny, logiczny dokument. Każdy fragment pochodzi z innego źródła AI.

INSTRUKCJE:
1. Połącz wszystkie fragmenty w logiczną całość
2. Usuń powtórzenia i sprzeczności
3. Zachowaj styl akademicki/edukacyjny
4. Dodaj płynne przejścia między sekcjami
5. Upewnij się, że tekst jest spójny tematycznie

FRAGMENTY DO POŁĄCZENIA:
"""
        
        for i, text in enumerate(collected_texts):
            if text:
                merge_prompt += f"\n\n--- Fragment {i+1} ---\n{text}\n"
        
        if chunk_metadata:
            merge_prompt += f"\n\nMETADANE CHUNKÓW:\n{json.dumps(chunk_metadata, indent=2)}\n"
        
        merge_prompt += "\n\nPOŁĄCZONY TEKST:"
        
        logger.info(f"Wysyłanie {len(collected_texts)} fragmentów do Qwen LLM w celu połączenia...")
        
        # Wyślij zapytanie do master node
        merged_text = self.send_query_to_node(master_node, merge_prompt)
        
        if merged_text:
            logger.info(f"Otrzymano połączony tekst ({len(merged_text)} znaków)")
        else:
            logger.error("Nie otrzymano połączonego tekstu z Qwen LLM")
        
        return merged_text
    
    def upload_to_moodle(self, text: str, filename: Optional[str] = None) -> bool:
        """
        Wysyła połączony tekst do Moodle course activity
        
        Args:
            text: Tekst do wysłania
            filename: Nazwa pliku (opcjonalnie)
            
        Returns:
            True jeśli wysyłka powiodła się
        """
        try:
            import requests
            
            moodle_config = self.config.get("moodle", {})
            moodle_url = moodle_config.get("url", "")
            moodle_token = moodle_config.get("token", "")
            course_id = moodle_config.get("course_id", "")
            
            if not moodle_url or not moodle_token:
                logger.error("Brak konfiguracji Moodle w config.json")
                return False
            
            # Zapisz tekst do tymczasowego pliku
            if not filename:
                filename = f"merged_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            temp_file = RESULTS_DIR / filename
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            logger.info(f"Wysyłanie pliku {filename} do Moodle...")
            
            # Encode pliku do base64
            import base64
            with open(temp_file, 'rb') as f:
                file_content = f.read()
            file_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # API call do Moodle
            response = requests.post(
                f"{moodle_url}/webservice/rest/server.php",
                data={
                    "wstoken": moodle_token,
                    "wsfunction": "core_user_upload_private_file",
                    "moodlewsrestformat": "json",
                    "itemid": 0,
                    "filename": filename,
                    "filepath": "/",
                    "filecontent": file_base64
                },
                timeout=60
            )
            
            result = response.json()
            
            if "exception" in result:
                logger.error(f"Błąd Moodle: {result.get('message', 'Nieznany błąd')}")
                return False
            
            file_id = result.get("id")
            if file_id:
                logger.info(f"Plik wysłany pomyślnie do Moodle (ID: {file_id})")
                
                # Opcjonalnie: dodaj plik do kursu
                if course_id:
                    self._add_file_to_course(moodle_url, moodle_token, course_id, file_id, filename)
                
                return True
            else:
                logger.error("Nie otrzymano ID pliku z Moodle")
                return False
                
        except Exception as e:
            logger.error(f"Błąd podczas wysyłki do Moodle: {e}")
            return False
    
    def _add_file_to_course(self, moodle_url: str, token: str, course_id: str, file_id: int, filename: str):
        """Dodaje plik do sekcji kursu Moodle"""
        try:
            section_id = self.config.get("moodle", {}).get("section_id", "")
            if not section_id:
                return
            
            requests.post(
                f"{moodle_url}/webservice/rest/server.php",
                data={
                    "wstoken": token,
                    "wsfunction": "core_course_add_contents_item",
                    "moodlewsrestformat": "json",
                    "courseid": course_id,
                    "section": section_id,
                    "module": "file",
                    "name": filename,
                    "contents[0][type]": "file",
                    "contents[0][file]": file_id
                },
                timeout=30
            )
            logger.info(f"Plik dodany do sekcji {section_id} kursu {course_id}")
        except Exception as e:
            logger.warning(f"Nie udało się dodać pliku do sekcji kursu: {e}")
    
    def process_cluster_sequential(self, queries: List[str]) -> List[Dict]:
        """
        Przetwarza zapytania szeregowo na wszystkich node'ach klastra
        
        Args:
            queries: Lista zapytań
            
        Returns:
            Lista wyników z wszystkich node'ów
        """
        cluster_config = self.config.get("cluster", {})
        nodes = cluster_config.get("nodes", [])
        
        logger.info(f"Rozpoczynanie przetwarzania szeregowego na {len(nodes)} node'ach")
        
        all_results = []
        
        for i, query in enumerate(queries):
            logger.info(f"[{i+1}/{len(queries)}] Przetwarzanie zapytania: {query[:50]}...")
            
            query_results = []
            
            # Wyślij to samo zapytanie do wszystkich node'ów
            for node in nodes:
                node_id = node["id"]
                node_type = node["type"]
                ai_platform = node.get("ai_platform", "coder.qwen.ai")
                
                logger.info(f"  -> Node {node_id} ({ai_platform})")
                
                result = {
                    "query_index": i,
                    "query": query,
                    "node_id": node_id,
                    "node_type": node_type,
                    "ai_platform": ai_platform,
                    "response": None,
                    "success": False,
                    "error": None,
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    # Dla RPi1 najpierw zaloguj jeśli trzeba
                    if node_type == "rpi1" and node_id not in self.sessions:
                        if not self.login_to_platform(node_id):
                            result["error"] = "Błąd logowania"
                            query_results.append(result)
                            continue
                    
                    response = self.send_query_to_node(node_id, query)
                    
                    if response:
                        result["response"] = response
                        result["success"] = True
                        logger.info(f"     ✓ Otrzymano odpowiedź ({len(response)} znaków)")
                    else:
                        result["error"] = "Brak odpowiedzi"
                        
                except Exception as e:
                    result["error"] = str(e)
                    logger.error(f"     ✗ Błąd: {e}")
                
                query_results.append(result)
                time.sleep(2)  # Opóźnienie między node'ami
            
            all_results.extend(query_results)
        
        return all_results
    
    def aggregate_and_merge_results(self, results: List[Dict], chunk_metadata: Dict = None) -> Optional[str]:
        """
        Agreguje wyniki z różnych AI i wysyła do Qwen LLM w celu połączenia
        
        Args:
            results: Lista wyników z wszystkich node'ów
            chunk_metadata: Metadane o chunkach (opcjonalnie)
            
        Returns:
            Połączony tekst lub None
        """
        # Najpierw zagreguj wyniki
        aggregated = self.aggregate_results(results)
        
        # Zebranie wszystkich odpowiedzi tekstowych
        collected_texts = []
        for query_data in aggregated.get("queries", []):
            for platform, response_data in query_data.get("ai_responses", {}).items():
                if response_data.get("response"):
                    collected_texts.append(response_data["response"])
        
        if not collected_texts:
            logger.error("Brak tekstów do połączenia")
            return None
        
        logger.info(f"Zebrano {len(collected_texts)} fragmentów do połączenia")
        
        # Wyślij do Qwen LLM w celu połączenia
        merged_text = self.merge_texts_with_qwen(collected_texts, chunk_metadata)
        
        return merged_text
    
    def process_full_pipeline(self, queries: List[str], chunk_metadata: Dict = None, upload_to_moodle_flag: bool = True) -> bool:
        """
        Pełny pipeline przetwarzania:
        1. Przetwarzanie szeregowe na wszystkich node'ach
        2. Agregacja wyników
        3. Łączenie tekstów przez Qwen LLM
        4. Wysyłka do Moodle
        
        Args:
            queries: Lista zapytań/chunków do przetworzenia
            chunk_metadata: Metadane o chunkach
            upload_to_moodle_flag: Czy wysłać wynik do Moodle
            
        Returns:
            True jeśli cały proces powiódł się
        """
        logger.info("=" * 80)
        logger.info("🚀 PEŁNY PIPELINE PRZETWARZANIA KLASTRA")
        logger.info("=" * 80)
        
        try:
            # Krok 1: Przetwarzanie szeregowe na wszystkich node'ach
            logger.info("\n[KROK 1/4] Przetwarzanie zapytań na wszystkich node'ach...")
            results = self.process_cluster_sequential(queries)
            
            # Sprawdź czy były sukcesy
            success_count = sum(1 for r in results if r.get("success"))
            if success_count == 0:
                logger.error("Żaden node nie zwrócił poprawnej odpowiedzi")
                return False
            
            logger.info(f"[KROK 1/4] ✓ Otrzymano {success_count} odpowiedzi")
            
            # Krok 2: Agregacja i łączenie tekstów
            logger.info("\n[KROK 2/4] Agregacja i łączenie tekstów przez Qwen LLM...")
            merged_text = self.aggregate_and_merge_results(results, chunk_metadata)
            
            if not merged_text:
                logger.error("Nie udało się połączyć tekstów")
                return False
            
            logger.info(f"[KROK 2/4] ✓ Połączony tekst ({len(merged_text)} znaków)")
            
            # Krok 3: Zapisz połączony tekst
            logger.info("\n[KROK 3/4] Zapisywanie połączonego tekstu...")
            output_file = RESULTS_DIR / f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(merged_text)
            logger.info(f"[KROK 3/4] ✓ Zapisano do {output_file}")
            
            # Krok 4: Wysyłka do Moodle (opcjonalnie)
            if upload_to_moodle_flag:
                logger.info("\n[KROK 4/4] Wysyłanie do Moodle...")
                if self.upload_to_moodle(merged_text, output_file.name):
                    logger.info("[KROK 4/4] ✓ Wysłano do Moodle")
                else:
                    logger.warning("[KROK 4/4] ⚠ Nie udało się wysłać do Moodle (sprawdź konfigurację)")
            else:
                logger.info("\n[KROK 4/4] Pominięto wysyłkę do Moodle")
            
            logger.info("\n" + "=" * 80)
            logger.info("✅ PEŁNY PIPELINE ZAKOŃCZONY SUKCESEM")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania pipeline: {e}")
            return False
    
    def aggregate_results(self, results: List[Dict]) -> Dict[str, Any]:
        """
        Agreguje wyniki z różnych AI w nodzie master
        
        Args:
            results: Lista wyników z wszystkich node'ów
            
        Returns:
            Zagregowane wyniki
        """
        cluster_config = self.config.get("cluster", {})
        master_node = cluster_config.get("master_node", "rpi4-1")
        
        logger.info(f"Agregacja wyników w nodzie master: {master_node}")
        
        # Grupuj wyniki według zapytania
        queries_results: Dict[int, List[Dict]] = {}
        for result in results:
            q_idx = result["query_index"]
            if q_idx not in queries_results:
                queries_results[q_idx] = []
            queries_results[q_idx].append(result)
        
        aggregated = {
            "timestamp": datetime.now().isoformat(),
            "master_node": master_node,
            "total_queries": len(queries_results),
            "total_responses": len([r for r in results if r["success"]]),
            "queries": []
        }
        
        for q_idx in sorted(queries_results.keys()):
            query_data = queries_results[q_idx][0] if queries_results[q_idx] else {}
            
            # Zbierz odpowiedzi z różnych AI
            ai_responses = {}
            for result in queries_results[q_idx]:
                platform = result.get("ai_platform", "unknown")
                if result.get("success") and result.get("response"):
                    ai_responses[platform] = {
                        "response": result["response"],
                        "node_id": result["node_id"],
                        "length": len(result["response"])
                    }
            
            aggregated["queries"].append({
                "query_index": q_idx,
                "query": query_data.get("query", ""),
                "ai_responses": ai_responses,
                "successful_platforms": list(ai_responses.keys()),
                "failed_platforms": [
                    r["ai_platform"] for r in queries_results[q_idx] 
                    if not r.get("success")
                ]
            })
        
        # Zapisz zagregowane wyniki
        output_file = RESULTS_DIR / f"aggregated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(aggregated, f, indent=2, ensure_ascii=False)
            logger.info(f"Zapisano zagregowane wyniki do {output_file}")
        except Exception as e:
            logger.error(f"Błąd zapisu zagregowanych wyników: {e}")
        
        return aggregated
    
    def close_all(self):
        """Zamyka wszystkie sesje"""
        for node_id, session in self.sessions.items():
            logger.info(f"Zamykanie sesji dla {node_id}")
            session.close()
        self.sessions.clear()


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
    
    parser = argparse.ArgumentParser(
        description='Qwen Coder AI Integration - Multi-Platform Cluster',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python qwen_coder_integration.py --test
  python qwen_coder_integration.py --query "Jaki jest najlepszy sposób na optymalizację kodu Python?"
  python qwen_coder_integration.py --multi --cluster-test
  python qwen_coder_integration.py --multi --batch queries.json
  python qwen_coder_integration.py --aggregate results.json
        """
    )
    parser.add_argument('--config', type=str, help='Ścieżka do pliku konfiguracyjnego')
    parser.add_argument('--test', action='store_true', help='Uruchom test logowania do coder.qwen.ai')
    parser.add_argument('--query', type=str, help='Pojedyncze zapytanie do wysłania')
    parser.add_argument('--batch', type=str, help='Plik JSON z listą zapytań')
    
    # Opcje dla multi-platform cluster
    parser.add_argument('--multi', action='store_true', help='Tryb multi-platform (wszystkie AI)')
    parser.add_argument('--cluster-test', action='store_true', help='Test klastra z wszystkimi node\'ami')
    parser.add_argument('--aggregate', type=str, help='Agreguj wyniki z pliku JSON')
    parser.add_argument('--node', type=str, help='ID konkretnego node\'a do testu')

    args = parser.parse_args()
    
    config_path = Path(args.config) if args.config else None
    
    try:
        if args.multi or args.cluster_test:
            # Tryb multi-platform z agregacją wyników
            logger.info("=" * 80)
            logger.info("🚀 MULTI-PLATFORM CLUSTER TEST - 3x RPi4 + 3x RPi1")
            logger.info("=" * 80)
            
            multi_ai = MultiAIIntegration(config_path)
            
            try:
                # Testowe zapytania
                if args.cluster_test:
                    queries = [
                        "Wyjaśnij czym jest rekurencja w programowaniu",
                        "Jak optimize'ować zapytania SQL?",
                        "Napisz funkcję Python obliczającą silnię"
                    ]
                elif args.batch:
                    batch_file = Path(args.batch)
                    if batch_file.exists():
                        with open(batch_file, 'r', encoding='utf-8') as f:
                            queries = json.load(f)
                        if not isinstance(queries, list):
                            print("❌ Plik batch powinien zawierać listę zapytań")
                            sys.exit(1)
                    else:
                        print(f"❌ Plik nie istnieje: {batch_file}")
                        sys.exit(1)
                else:
                    queries = ["Testowe zapytanie do wszystkich platform AI"]
                
                # Przetwarzanie szeregowe na całym klastrze
                results = multi_ai.process_cluster_sequential(queries)
                
                # Agregacja wyników w nodzie master
                aggregated = multi_ai.aggregate_results(results)
                
                # Podsumowanie
                logger.info("=" * 80)
                logger.info("📊 PODSUMOWANIE")
                logger.info("=" * 80)
                logger.info(f"Total queries: {aggregated['total_queries']}")
                logger.info(f"Total responses: {aggregated['total_responses']}")
                logger.info(f"Master node: {aggregated['master_node']}")
                
                for q in aggregated['queries']:
                    logger.info(f"\nQuery {q['query_index']}: {q['query'][:50]}...")
                    logger.info(f"  ✓ Successful platforms: {q['successful_platforms']}")
                    if q['failed_platforms']:
                        logger.info(f"  ✗ Failed platforms: {q['failed_platforms']}")
                
                logger.info("=" * 80)
                
            finally:
                multi_ai.close_all()
        
        elif args.aggregate:
            # Agregacja istniejących wyników
            results_file = Path(args.aggregate)
            if results_file.exists():
                with open(results_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                multi_ai = MultiAIIntegration(config_path)
                aggregated = multi_ai.aggregate_results(results)
                multi_ai.close_all()
            else:
                print(f"❌ Plik nie istnieje: {results_file}")
        
        elif args.test:
            # Test logowania (tryb legacy)
            integrator = QwenCoderIntegration(config_path)
            print("Test logowania do coder.qwen.ai...")
            if integrator.initialize_browser("selenium"):
                if integrator.login():
                    print("✅ Logowanie zakończone sukcesem!")
                else:
                    print("❌ Logowanie nieudane")
            else:
                print("❌ Nie udało się zainicjalizować przeglądarki")
            integrator.close()

        elif args.query:
            # Pojedyncze zapytanie (tryb legacy)
            integrator = QwenCoderIntegration(config_path)
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
            integrator.close()

        elif args.batch:
            # Batch zapytań z pliku (tryb legacy)
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

    except KeyboardInterrupt:
        logger.info("\n⚠️ Przerwano przez użytkownika")
    except Exception as e:
        logger.error(f"Błąd: {e}")
        raise
