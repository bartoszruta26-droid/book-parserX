# Qwen Coder AI Integration - Instrukcja Użycia

## 📖 Opis

Moduł `qwen_coder_integration.py` zapewnia integrację z platformą **coder.qwen.ai**, umożliwiając:

- Automatyczne logowanie przy użyciu danych z pliku konfiguracyjnego
- Wysyłanie zapytań do modelu Qwen Coder przez przeglądarkę
- Odbieranie i przetwarzanie odpowiedzi
- Przetwarzanie szeregowe na klastrze 6 node'ów (3x Raspberry Pi 4 + 3x Raspberry Pi 1)
- Logowanie wszystkich zapytań i odpowiedzi

## 🔧 Instalacja

### 1. Zainstaluj zależności

```bash
pip install -r requirements.txt
```

Nowe zależności dla integracji z browserem:
- `selenium>=4.15.0` - automatyzacja przeglądarki
- `playwright>=1.40.0` - alternatywa dla Selenium
- `webdriver-manager>=4.0.0` - zarządzanie driverami przeglądarek

### 2. Skonfiguruj dane logowania

Skopiuj przykładowy plik konfiguracyjny i edytuj go:

```bash
cp config.json.example config.json
nano config.json
```

W pliku `config.json` ustaw swoje dane:

```json
{
  "qwen_coder": {
    "email": "bartosz.ruta26@gmail.com",
    "password": "TWOJE_PRAWDZIWE_HASLO",
    "base_url": "https://coder.qwen.ai",
    "login_url": "https://coder.qwen.ai/login"
  }
}
```

**⚠️ UWAGA:** Nigdy nie commituj pliku `config.json` z prawdziwymi hasłami do repozytorium!

## 🚀 Szybki Start

### Test logowania

```bash
python3 qwen_coder_integration.py --test
```

### Pojedyncze zapytanie

```bash
python3 qwen_coder_integration.py --query "Napisz funkcję Python sortującą listę liczb"
```

### Przetwarzanie batchowe z pliku

Przygotuj plik JSON z listą zapytań:

```json
[
  "Wyjaśnij czym jest rekurencja",
  "Napisz klasę Stack w Pythonie",
  "Jak zoptymalizować zapytania SQL?"
]
```

Uruchom przetwarzanie:

```bash
python3 qwen_coder_integration.py --batch queries.json
```

## 🏗️ Architektura Klastra

### Konfiguracja node'ów

Domyślna konfiguracja obejmuje 6 node'ów:

| ID | Typ | Host | Rdzenie | RAM |
|----|-----|------|---------|-----|
| rpi4-1 | rpi4 | 192.168.1.101 | 4 | 4GB/8GB |
| rpi4-2 | rpi4 | 192.168.1.102 | 4 | 4GB/8GB |
| rpi4-3 | rpi4 | 192.168.1.103 | 4 | 4GB/8GB |
| rpi1-1 | rpi1 | 192.168.1.104 | 1 | 512MB |
| rpi1-2 | rpi1 | 192.168.1.105 | 1 | 512MB |
| rpi1-3 | rpi1 | 192.168.1.106 | 1 | 512MB |

### Tryby pracy

1. **Serial (domyślny)** - Zadania przetwarzane jedno po drugim, round-robin między node'ami
2. **Parallel** - Wszystkie node'y pracują równolegle
3. **Hybrid** - RPi4 pracują równolegle, RPi1 szeregowo

## 📋 Przykłady Użycia w Kodzie

### Podstawowe użycie

```python
from qwen_coder_integration import QwenCoderIntegration

# Inicjalizacja
integrator = QwenCoderIntegration()

# Inicjalizacja przeglądarki
integrator.initialize_browser("selenium")

# Logowanie
if integrator.login():
    print("Zalogowano pomyślnie!")
    
    # Wysyłanie zapytania
    response = integrator.send_query("Napisz hello world w Pythonie")
    
    if response:
        print(f"Odpowiedź: {response}")

# Zamknięcie
integrator.close()
```

### Przetwarzanie szeregowe

```python
from qwen_coder_integration import run_sequential_pipeline

queries = [
    "Wyjaśnij programowanie obiektowe",
    "Napisz funkcję obliczającą silnię",
    "Jak działa garbage collection w Pythonie?"
]

run_sequential_pipeline(queries, config_path="config.json")
```

### Zaawansowane - ręczne zarządzanie

```python
from qwen_coder_integration import QwenCoderIntegration

integrator = QwenCoderIntegration("config.json")

try:
    # Inicjalizacja Playwright zamiast Selenium
    integrator.initialize_browser("playwright")
    
    # Logowanie
    if not integrator.login():
        raise Exception("Logowanie nieudane")
    
    # Wysłanie wielu zapytań
    queries = ["Query 1", "Query 2", "Query 3"]
    results = integrator.process_batch_sequential(
        queries,
        node_ids=["rpi4-1", "rpi4-2"]  # Tylko konkretne node'y
    )
    
    # Analiza wyników
    for result in results:
        if result["success"]:
            print(f"Node {result['node_id']}: OK ({len(result['response'])} znaków)")
        else:
            print(f"Node {result['node_id']}: BŁĄD - {result['error']}")

finally:
    integrator.close()
```

## 📁 Struktura Plików

```
/workspace/
├── qwen_coder_integration.py    # Główny moduł integracji
├── config.json                  # Plik konfiguracyjny (nie commitować!)
├── config.json.example          # Przykład konfiguracji
├── qwen_sessions/               # Sesje logowania
│   └── session_YYYYMMDD_HHMMSS.json
├── logs/                        # Logi zapytań i odpowiedzi
│   ├── qwen_queries_YYYYMMDD.jsonl
│   └── results_YYYYMMDD_HHMMSS.json
└── requirements.txt             # Zależności
```

## 🔍 Logi i Monitorowanie

### Logi zapytań

Każde zapytanie i odpowiedź są logowane do pliku JSONL:

```bash
cat logs/qwen_queries_$(date +%Y%m%d).jsonl | jq .
```

### Wyniki przetwarzania batchowego

```bash
cat logs/results_*.json | jq '.[] | select(.success == true)'
```

## ⚠️ Rozwiązywanie Problemów

### Błąd: "Selenium nie jest zainstalowane"

```bash
pip install selenium webdriver-manager
```

### Błąd: "Brak ChromeDriver"

Zainstaluj ChromeDriver:

```bash
# Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# Lub użyj webdriver-manager
pip install webdriver-manager
```

### Błąd: "Logowanie nieudane"

1. Sprawdź dane logowania w `config.json`
2. Upewnij się że masz aktywne połączenie internetowe
3. Spróbuj zalogować się manualnie na https://coder.qwen.ai

### Błąd: "Timeout oczekiwania na odpowiedź"

Zwiększ timeout w konfiguracji:

```json
{
  "browser": {
    "timeout": 120
  },
  "processing": {
    "task_timeout": 600
  }
}
```

## 🔒 Bezpieczeństwo

1. **Nigdy nie commituj** `config.json` z hasłami
2. Dodaj `config.json` do `.gitignore`
3. Ustaw uprawnienia: `chmod 600 config.json`
4. Rozważ użycie zmiennych środowiskowych dla wrażliwych danych

## 📊 Wydajność

### Zalecenia dla klastra Raspberry Pi

1. **RPi4** - Używaj do cięższych zadań (większy kontekst, złożone zapytania)
2. **RPi1** - Używaj do prostych, krótkich zapytań
3. **Tryb szeregowy** - Najbardziej stabilny dla heterogenicznego klastra
4. **Opóźnienia** - Dostosuj `retry_delay` aby uniknąć przeciążenia

## 🤝 Integracja z WebUI

Moduł można zintegrować z istniejącym `webui.py`:

```python
# W webui.py dodaj import
from qwen_coder_integration import QwenCoderIntegration

# Dodaj handler w WebUIHandler
def handle_qwen_query(self, post_data):
    params = parse_qs(post_data)
    query = params.get('query', [''])[0]
    
    integrator = QwenCoderIntegration()
    try:
        if integrator.initialize_browser("selenium") and integrator.login():
            response = integrator.send_query(query)
            self.send_json_response({
                "success": response is not None,
                "response": response
            })
    finally:
        integrator.close()
```

## 📞 Kontakt

Autor: bartosz.ruta26@gmail.com

---

**Licencja:** MIT  
**Wersja:** 1.0.0  
**Data:** 2026
