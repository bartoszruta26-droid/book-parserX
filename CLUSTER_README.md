# Distributed AI Cluster - README

## Architektura

System składa się z:
- **1x Master Node** (dowolne RPi) - zarządza całym procesem
- **3x Raspberry Pi 4** - uruchamiają lokalny model Qwen LLM
- **3x Raspberry Pi 1** - komunikują się z webowymi AI (ChatGPT, Grok, Qwen Web)

## Przepływ Danych

1. **Chunking**: Master dzieli plik wejściowy na mniejsze części
2. **Dystrybucja LLM**: Chunki są wysyłane do RPi4 w trybie dynamicznego load balancingu
   - Jeśli RPi4 jest zajęty, zadanie czeka w kolejce
   - Wolne RPi4 natychmiast otrzymuje zadanie
3. **Web Scraping**: RPi1 logują się na strony AI i pobierają informacje
4. **Agregacja**: Master zbiera wszystkie wyniki
5. **Finalizacja**: Połączony tekst jest wysyłany do wolnego RPi4 w celu podsumowania
6. **Moodle**: Gotowy plik jest wysyłany do aktywności w Moodle

## Instalacja

### Na wszystkich node'ach:
```bash
pip install flask requests
```

### Na RPi1 (dodatkowo):
```bash
pip install selenium playwright
playwright install
```

### Na RPi4 (dodatkowo):
```bash
# Zainstaluj Ollama lub inny serwer LLM
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

## Konfiguracja

### Master Node (`config.json`):
```json
{
  "master": {"ip": "192.168.1.100", "port": 5000},
  "moodle": {
    "url": "https://twoje-moodle.pl",
    "token": "TOKEN",
    "course_id": 1,
    "activity_id": 123
  },
  "nodes": [
    {"id": "rpi4-1", "type": "rpi4", "ip": "192.168.1.101", "port": 5001, "role": "llm_worker"},
    {"id": "rpi4-2", "type": "rpi4", "ip": "192.168.1.102", "port": 5001, "role": "llm_worker"},
    {"id": "rpi4-3", "type": "rpi4", "ip": "192.168.1.103", "port": 5001, "role": "llm_worker"},
    {"id": "rpi1-1", "type": "rpi1", "ip": "192.168.1.104", "port": 5002, "role": "web_scraper", 
     "credentials": {"email": "user1@example.com", "password": "pass1"}, 
     "targets": ["chatgpt.com", "grok.com"]}
  ]
}
```

### Worker Node (`worker_config.json`):
```json
{
  "node_id": "rpi4-1",
  "type": "rpi4",
  "llm_port": 5001
}
```

## Uruchomienie

### Na każdym Worker Node:
```bash
python worker_node.py
```

### Na Master Node:
```bash
python qwen_cluster_master.py --file input.txt --output result.txt
```

## Load Balancing

System automatycznie wykrywa wolne RPi4:
- Każde RPi4 raportuje status (idle/busy)
- Master przydziela zadania tylko wolnym node'om
- Jeśli wszystkie RPi4 są zajęte, zadania czekają w kolejce
- Po zakończeniu przetwarzania, node wraca do puli wolnych

## Przykładowe Użycie

```bash
# Przetwarzanie dużego pliku
python qwen_cluster_master.py --file dissertation.pdf --output final.txt

# Z innym configiem
python qwen_cluster_master.py --file text.txt --config custom_config.json
```

## Wymagania Sprzętowe

- **RPi4**: Minimum 4GB RAM dla modelu 7B, zalecane 8GB
- **RPi1**: Wystarczające do browser automation (mogą być wolne)
- **Sieć**: Wszystkie node'y w tej samej sieci LAN

## Rozwiązywanie Problemów

1. **Node nie odpowiada**: Sprawdź `curl http://<ip>:<port>/health`
2. **LLM za wolny**: Zmniejsz rozmiar chunku w `chunk_file()`
3. **Błąd logowania**: Zweryfikuj dane w `config.json`
