# Book Rewriting Pipeline z integracją Moodle

## 📖 Opis Projektu

Projekt **Book Rewriting Pipeline** to zaawansowany system do przepisywania i przetwarzania książek, wykorzystujący potok (pipeline) złożony z modeli AI Qwen oraz automatyczną wysyłkę do platformy Moodle.

### 🔑 Kluczowe Funkcje

1. **Konwersja plików** - Obsługa wielu formatów (PDF, DOC, DOCX, ODT, RTF, HTML, MD)
2. **Chunking** - Inteligentny podział tekstu na chunki ~4096 tokenów z metadanymi
3. **Przepisywanie AI** - Wykorzystanie modeli qwen-coder i qwen3.6-35B-A3B
4. **Składanie książki** - Automatyczne łączenie przetworzonych chunków
5. **Upload do Moodle** - Wysyłka gotowych materiałów przez Web Services API

### 🏗️ Architektura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐     ┌──────────┐
│ qwen-agent  │ --> │ qwen-coder  │ --> │ qwen3.6-35B-A3B │ --> │  Moodle  │
│ (Koordynator)│     │(Struktura)  │     │   (Treść)       │     │  Upload  │
└─────────────┘     └─────────────┘     └─────────────────┘     └──────────┘
```

## 📁 Struktura Projektu

```
/workspace/
├── README.md               # Ten plik
├── install.sh              # Instalator i konfigurator [ZAKTUALIZOWANY]
├── full_workflow.sh        # Kompletny workflow jedną komendą [NOWOŚĆ]
├── upload_to_moodle.sh     # Wysyłka do Moodle [NOWOŚĆ]
├── pipeline.sh             # Główny skrypt z interfejsem TUI
├── convert_to_txt.sh       # Konwersja plików na TXT
├── chunk_script.sh         # Dzielenie na chunki z metadanymi JSON
├── rewrite_chunks.sh       # Przepisywanie chunków przez AI
├── webui.py                # Interfejs webowy (Gradio)
├── config.sh.example       # Przykładowa konfiguracja
├── requirements.txt        # Zależności Python
├── input/                  # Pliki wejściowe (książki)
├── tmp/                    # Pliki tymczasowe (.txt po konwersji)
├── chunk/                  # Chunki z metadanymi JSON
├── output/                 # Przetworzone chunki (JSON)
├── finish/                 # Gotowe książki (złożone z chunków)
└── logs/                   # Logi procesu
```

## 🚀 Szybki Start

### 1. Instalacja

```bash
# Klonowanie repozytorium
git clone <repository-url>
cd book-parserX

# Uruchomienie instalatora
./install.sh

# Lub z dodatkowymi opcjami:
./install.sh --moodle --configure --verbose
```

### 2. Konfiguracja

```bash
# Edycja pliku konfiguracyjnego
nano config.sh

# Lub interaktywna konfiguracja:
./install.sh --configure
```

**Wymagane zmienne w `config.sh`:**
```bash
# API Qwen
QWEN_API_KEY="twój-klucz-api"
QWEN_CODER_URL="http://localhost:8000/v1/chat/completions"
QWEN_LARGE_MODEL_URL="http://localhost:8000/v1/chat/completions"

# Moodle (opcjonalne)
MOODLE_URL="https://twoje-moodle.pl"
MOODLE_TOKEN="twój-token-web-services"
MOODLE_COURSE_ID="123"
```

### 3. Uruchomienie

```bash
# Pełny workflow jedną komendą:
./full_workflow.sh

# Lub krok po kroku przez TUI:
./pipeline.sh

# Lub interfejs webowy:
./pipeline.sh webui
```

## 📋 Szczegółowy Proces

### Krok 1: Przygotowanie plików

Umieść pliki książek w katalogu `input/`:
```bash
cp twoja-ksiazka.pdf input/
```

### Krok 2: Konwersja do TXT

```bash
./convert_to_txt.sh -v
```

**Obsługiwane formaty:** `.doc`, `.docx`, `.pdf`, `.odt`, `.rtf`, `.html`, `.md`, `.txt`

### Krok 3: Podział na Chunki

```bash
./chunk_script.sh /tmp/book.txt
```

Każdy chunk zawiera metadane JSON:
- `chunk_id` - unikalny identyfikator
- `token_count` - liczba tokenów
- `previous_chunk` / `next_chunk` - linki do sąsiednich chunków
- `line_start` / `line_end` - zakres linii
- Kontekst całej książki

### Krok 4: Przepisywanie przez AI

```bash
./rewrite_chunks.sh
```

**Proces dwuetapowy:**
1. **qwen-coder** - analiza struktury, formatowanie, metadane
2. **qwen3.6-35B-A3B** - głęboka analiza treści i przepisanie

### Krok 5: Składanie i Upload do Moodle

Automatycznie wykonywane przez `full_workflow.sh`:
```bash
./full_workflow.sh
```

Lub ręcznie:
```bash
# Złożenie książki
./pipeline.sh cli

# Upload do Moodle
./upload_to_moodle.sh -v
```

## 🛠️ Tryby Uruchomienia

### full_workflow.sh - Kompletny Workflow

```bash
# Pełny proces
./full_workflow.sh

# Ze szczegółowym logowaniem
./full_workflow.sh -v

# Bez przepisywania AI
./full_workflow.sh --skip-rewrite

# Tylko upload do Moodle
./full_workflow.sh --moodle-only

# Pomoc
./full_workflow.sh -h
```

**Opcje:**
- `-v, --verbose` - Tryb szczegółowy
- `-c, --skip-conversion` - Pominięcie konwersji
- `-u, --skip-chunking` - Pominięcie chunkingu
- `-r, --skip-rewrite` - Pominięcie przepisywania AI
- `-m, --skip-moodle` - Pominięcie wysyłki do Moodle
- `-o, --moodle-only` - Tylko wysyłka do Moodle

### pipeline.sh - Interfejs TUI

```bash
# Tryb interaktywny (domyślny)
./pipeline.sh

# Tryb CLI
./pipeline.sh cli

# Interfejs webowy
./pipeline.sh webui 8080

# Daemon (usługa w tle)
./pipeline.sh daemon start
```

## ⚙️ Konfiguracja

### Zmienne Środowiskowe Qwen

| Zmienna | Opis | Domyślna wartość |
|---------|------|------------------|
| `QWEN_API_KEY` | Klucz API Alibaba Cloud | - |
| `QWEN_AGENT_URL` | Endpoint qwen-agent | localhost:8000 |
| `QWEN_CODER_URL` | Endpoint qwen-coder | localhost:8000 |
| `QWEN_LARGE_MODEL_URL` | Endpoint qwen3.6 | localhost:8000 |
| `MAX_TOKENS` | Maksymalna liczba tokenów | 4096 |
| `TEMPERATURE` | Kreatywność modelu | 0.7 |

### Zmienne Środowiskowe Moodle

| Zmienna | Opis | Wymagana |
|---------|------|----------|
| `MOODLE_URL` | URL instancji Moodle | Tak |
| `MOODLE_TOKEN` | Token Web Services | Tak |
| `MOODLE_COURSE_ID` | ID kursu docelowego | Tak |
| `MOODLE_SECTION_ID` | ID sekcji (opcjonalnie) | Nie |

**Jak uzyskać token Moodle:**
1. Zaloguj się jako administrator
2. Przejdź do: *Administracja > Pluginy > Web services > Zarządzaj tokenami*
3. Utwórz nowy token dla użytkownika z uprawnieniami
4. Włącz funkcję `core_user_upload_private_file`

## 🔧 Instalacja Krok po Kroku

### 1. Zależności Systemowe

**Debian/Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y curl jq git wget unzip python3 python3-pip python3-venv pandoc poppler-utils
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y curl jq git wget unzip python3 python3-pip
```

### 2. Środowisko Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Katalogi Robocze

```bash
mkdir -p input tmp chunk output finish logs temp
```

### 4. Instalator Automatyczny

```bash
# Standardowa instalacja
./install.sh

# Z konfiguracją API
./install.sh --configure

# Z wsparciem Moodle
./install.sh --moodle

# Pełna instalacja
./install.sh --models --configure --moodle --verbose
```

## 📊 Monitorowanie i Logi

Logi są zapisywane w `logs/`:
- `pipeline.log` - Ogólne logi procesu
- `rewrite.log` - Logi z przepisywania AI
- `moodle.log` - Logi z uploadu do Moodle

Podgląd logów:
```bash
tail -f logs/pipeline.log
```

## 🐛 Rozwiązywanie Problemów

### Brak odpowiedzi od API
- Sprawdź połączenie sieciowe
- Zweryfikuj klucze API w `config.sh`
- Sprawdź limity rate-limiting

### Błąd uploadu do Moodle
- Upewnij się że Web Services są włączone
- Sprawdź czy token ma odpowiednie uprawnienia
- Zweryfikuj `MOODLE_COURSE_ID`

### Ucięty output
- Zwiększ `MAX_TOKENS` w konfiguracji
- Podziel tekst na mniejsze segmenty

### Niska jakość przetwarzania
- Dostosuj parametr `TEMPERATURE` (0.3-0.8)
- Sprawdź prompt engineering w skryptach

## 🔒 Bezpieczeństwo

- **Nigdy nie commituj** `config.sh` z prawdziwymi kluczami
- Dodaj `config.sh` do `.gitignore`
- Używaj zmiennych środowiskowych dla wrażliwych danych
- Ustaw uprawnienia: `chmod 600 config.sh`

## 📈 Wydajność

**Optymalizacje:**
- Równoległe przetwarzanie chunków (w przygotowaniu)
- Cache przetworzonych chunków
- Batch upload do Moodle

**Zalecenia:**
- Używaj lokalnego serwera modeli (Ollama/vLLM) dla lepszej wydajności
- Dostosuj rozmiar chunka do dostępnej pamięci
- Używaj trybu `--skip-*` do testowania poszczególnych etapów

## 🤝 Wkład w Projekt

1. Fork repozytorium
2. Utwórz branch (`git checkout -b feature/nowa-funkcjonalnosc`)
3. Commit zmian (`git commit -m 'Dodano nową funkcjonalność'`)
4. Push (`git push origin feature/nowa-funkcjonalnosc`)
5. Otwórz Pull Request

## 📄 Licencja

MIT License - zobacz plik [LICENSE](LICENSE)

## 📞 Kontakt

W przypadku pytań i problemów proszę otworzyć issue w repozytorium.

---

**Uwaga**: Ten projekt wykorzystuje modele AI firmy Alibaba Cloud (Qwen). Upewnij się, że masz odpowiednie uprawnienia i klucze API przed użyciem.