# Multi-Platform AI Cluster - Dokumentacja

## Przegląd

Rozszerzony system integracji z wieloma platformami AI dla klastra Raspberry Pi (3x RPi4 + 3x RPi1).

### Architektura

```
┌─────────────────────────────────────────────────────────────────┐
│                        MASTER NODE (RPi4-1)                      │
│                     Agregacja wyników z wszystkich AI            │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────┴───────┐   ┌─────────┴─────────┐   ┌──────┴──────┐
│   RPi4-2      │   │     RPi4-3        │   │  RPi1-1     │
│   Local LLM   │   │     Local LLM     │   │  Qwen Coder │
│  llama-2-7b   │   │    llama-2-7b     │   │  coder.qwen.ai
└───────────────┘   └───────────────────┘   └─────────────┘
                                              
┌───────────────┐   ┌───────────────────┐
│   RPi1-2      │   │     RPi1-3        │
│   ChatGPT     │   │     Grok          │
│ chatgpt.com   │   │     grok.com      │
└───────────────┘   └───────────────────┘
```

## Funkcje

### Raspberry Pi 4 (3 sztuki)
- **AI Platform**: Local LLM
- **Model**: llama-2-7b (konfigurowalny)
- **Komunikacja**: HTTP API (port 5000)

### Raspberry Pi 1 (3 sztuki)
- **AI Platform**: Webowe AI
  - RPi1-1: coder.qwen.ai
  - RPi1-2: chatgpt.com
  - RPi1-3: grok.com
- **Logowanie**: Indywidualne dane dla każdego node'a
- **Automatyzacja**: Selenium/Playwright

## Konfiguracja

### Plik config.json

```json
{
  "credentials_profiles": {
    "qwen_profile_1": {
      "platform": "coder.qwen.ai",
      "email": "twoj_email@example.com",
      "password": "twoje_haslo"
    },
    "chatgpt_profile_1": {
      "platform": "chatgpt.com",
      "email": "chatgpt_email@example.com",
      "password": "chatgpt_haslo"
    },
    "grok_profile_1": {
      "platform": "grok.com",
      "email": "grok_email@example.com",
      "password": "grok_haslo"
    }
  },
  "local_llm": {
    "enabled": true,
    "model": "llama-2-7b",
    "port": 5000,
    "host": "localhost",
    "api_endpoint": "http://localhost:5000/v1/chat/completions"
  },
  "cluster": {
    "nodes": [
      {
        "id": "rpi4-1",
        "type": "rpi4",
        "host": "192.168.1.101",
        "ai_platform": "local_llm"
      },
      {
        "id": "rpi1-1",
        "type": "rpi1",
        "host": "192.168.1.104",
        "ai_platform": "coder.qwen.ai",
        "credentials_profile": "qwen_profile_1"
      }
      // ... więcej node'ów
    ],
    "master_node": "rpi4-1"
  }
}
```

## Użycie

### Tryb Multi-Platform (zalecany)

```bash
# Test całego klastra
python qwen_coder_integration.py --multi --cluster-test

# Przetwarzanie batcha zapytań
python qwen_coder_integration.py --multi --batch queries.json

# Agregacja istniejących wyników
python qwen_coder_integration.py --aggregate results.json
```

### Tryb Legacy (tylko Qwen)

```bash
# Test logowania
python qwen_coder_integration.py --test

# Pojedyncze zapytanie
python qwen_coder_integration.py --query "Twoje pytanie"

# Batch zapytań
python qwen_coder_integration.py --batch queries.json
```

## Struktura Wyników

### Plik zagregowany (results/aggregated_*.json)

```json
{
  "timestamp": "2026-05-11T07:12:28.771",
  "master_node": "rpi4-1",
  "total_queries": 3,
  "total_responses": 6,
  "queries": [
    {
      "query_index": 0,
      "query": "Wyjaśnij czym jest rekurencja...",
      "ai_responses": {
        "local_llm": {
          "response": "Rekurencja to...",
          "node_id": "rpi4-1",
          "length": 150
        },
        "coder.qwen.ai": {
          "response": "Rekurencja w programowaniu...",
          "node_id": "rpi1-1",
          "length": 200
        }
      },
      "successful_platforms": ["local_llm", "coder.qwen.ai"],
      "failed_platforms": []
    }
  ]
}
```

## Wymagania

### Python packages
```bash
pip install selenium playwright requests webdriver-manager
playwright install chromium
```

### Systemowe
- Chrome/Chromium
- Python 3.8+
- Dostęp do internetu (dla webowych AI)
- Lokalny serwer LLM (dla RPi4)

## Logowanie do Platform

Każdy node może mieć **inne dane logowania** do różnych platform:

| Node | Platforma | Email | Hasło |
|------|-----------|-------|-------|
| rpi1-1 | coder.qwen.ai | user1@example.com | *** |
| rpi1-2 | chatgpt.com | user2@example.com | *** |
| rpi1-3 | grok.com | user3@example.com | *** |

Dane konfiguruje się w sekcji `credentials_profiles` pliku `config.json`.

## Szeregowość Przetwarzania

Skrypt przetwarza zapytania **szeregowo**:
1. Wysyła to samo zapytanie do wszystkich 6 node'ów
2. Czeka na odpowiedź z każdego node'a
3. Agreguje wyniki w nodzie master (rpi4-1)
4. Zapisuje rezultaty do pliku JSON

Czas przetwarzania: ~2 sekundy na node = ~12 sekund na zapytanie

## API Endpoints

### Local LLM (RPi4)
```
POST http://localhost:5000/v1/chat/completions
Content-Type: application/json

{
  "model": "llama-2-7b",
  "messages": [{"role": "user", "content": "Pytanie"}],
  "max_tokens": 1024,
  "temperature": 0.7
}
```

### Web AI (RPi1)
- Automatyzacja przez przeglądarkę (Selenium/Playwright)
- Logowanie formularzem
- Wysyłanie zapytań przez UI
- Parsowanie odpowiedzi z DOM

## Rozwiązywanie Problemów

### Błąd: "Brak danych logowania"
- Sprawdź czy `credentials_profiles` ma wpis dla danego node'a
- Upewnij się że email i password są wypełnione

### Błąd: "Connection refused" (Local LLM)
- Uruchom serwer LLM na porcie 5000
- Sprawdź konfigurację `local_llm.api_endpoint`

### Błąd: "Nie udało się zainicjalizować przeglądarki"
- Zainstaluj Chrome/Chromium
- Uruchom `playwright install chromium`
- Sprawdź czy WebDriver jest dostępny

## Autor

bartosz.ruta26@gmail.com

## Licencja

MIT
