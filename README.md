# Book Rewriting Pipeline

## Opis Projektu

Projekt **Book Rewriting Pipeline** to system do przepisywania i przetwarzania książek, wykorzystujący potok (pipeline) złożony z trzech modeli AI:

1. **qwen-agent** - Agent zarządzający przepływem pracy i koordynujący zadania
2. **qwen-coder** - Model specjalizujący się w generowaniu i refaktoryzacji kodu
3. **qwen3.6-35B-A3B** - Duży model językowy do zaawansowanego przetwarzania tekstu

## Architektura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│ qwen-agent  │ --> │ qwen-coder  │ --> │ qwen3.6-35B-A3B │
│  (Koordynator) │     │  (Kod/Struktura)│     │  (Treść/Styl)   │
└─────────────┘     └─────────────┘     └─────────────────┘
```

## Wymagania

- Bash shell (GNU Bash 4.0+)
- curl lub wget
- jq (do parsowania JSON)
- Dostęp do API modeli Qwen

## Struktura Projektu

```
/workspace/
├── README.md           # Ten plik
├── pipeline.sh         # Główny skrypt potoku
├── config.sh           # Konfiguracja API i parametrów
├── input/              # Katalog z plikami wejściowymi (książki)
├── tmp/                # Pliki tymczasowe (.txt po konwersji)
├── chunk/              # Chunki po 4096 tokenów z metadanymi JSON
├── output/             # Katalog z przetworzonymi wynikami
├── logs/               # Logi z procesu przetwarzania
└── temp/               # Dodatkowe pliki robocze
```

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone <repository-url>
cd book-parserX
```

2. Utwórz niezbędne katalogi:
```bash
mkdir -p input tmp chunk output logs temp
```

3. Skonfiguruj zmienne środowiskowe w `config.sh`:
```bash
cp config.sh.example config.sh
# Edytuj config.sh i dodaj swoje klucze API
```

## Użycie

Skrypt automatycznie wczytuje pliki z katalogu `/input` i zapisuje je jako `.txt` w katalogu `/tmp`.

### Tryby uruchomienia

Skrypt `pipeline.sh` obsługuje cztery tryby pracy:

#### 1. CLI (Command Line Interface)

Tryb tekstowy w terminalu - domyślny tryb działania:

```bash
# Uruchomienie w trybie interaktywnym CLI
./pipeline.sh cli

# Lub bezpośrednio (domyślny tryb)
./pipeline.sh

# Z konkretnym plikiem
./pipeline.sh cli input/book.txt

# Tryb szczegółowy
./pipeline.sh cli -v
```

#### 2. GUI / TUI (Graphical / Text User Interface)

Tryb z interfejsem użytkownika:

```bash
# Uruchomienie z interfejsem TUI (tekstowym)
./pipeline.sh tui

# Uruchomienie z interfejsem GUI (graficznym, jeśli dostępny)
./pipeline.sh gui
```

#### 3. WebUI (Web Interface)

Uruchomienie serwera webowego z interfejsem przeglądarkowym:

```bash
# Start serwera WebUI
./pipeline.sh webui

# Start na konkretnym porcie
./pipeline.sh webui --port 8080
```

Po uruchomieniu interfejs będzie dostępny pod adresem `http://localhost:8080` (lub inny określony port).

#### 4. Daemon (Tryb usługi)

Uruchomienie jako usługa w tle:

```bash
# Start w trybie daemon
./pipeline.sh daemon start

# Stop daemon
./pipeline.sh daemon stop

# Status daemon
./pipeline.sh daemon status

# Restart daemon
./pipeline.sh daemon restart
```

### Obsługiwane formaty plików

- `.doc` - Dokumenty Microsoft Word (starsze wersje)
- `.odt` - OpenDocument Text
- `.docx` - Dokumenty Microsoft Word (nowsze wersje)
- `.xls` - Arkusze kalkulacyjne Microsoft Excel (starsze wersje)
- `.xlsx` - Arkusze kalkulacyjne Microsoft Excel (nowsze wersje)
- `.pdf` - Dokumenty PDF
- `.txt` - Pliki tekstowe
- `.md` - Pliki Markdown

## Konfiguracja

Edytuj plik `config.sh`, aby ustawić:

- `QWEN_API_KEY` - Twój klucz API
- `QWEN_AGENT_URL` - Endpoint dla qwen-agent
- `QWEN_CODER_URL` - Endpoint dla qwen-coder
- `QWEN_LARGE_MODEL_URL` - Endpoint dla qwen3.6-35B-A3B
- `MAX_TOKENS` - Maksymalna liczba tokenów na żądanie
- `TEMPERATURE` - Parametr kreatywności modelu

## Jak działa Pipeline?

1. **Wczytanie i konwersja**: Pliki z katalogu `/input` są konwertowane do formatu `.txt` i zapisywane w `/tmp`
2. **Chunking**: Pliki z `/tmp` są dzielone na chunki po 4096 tokenów i zapisywane w katalogu `/chunk`
3. **Etap 1 - qwen-agent**: Analiza struktury książki, podział na rozdziały, identyfikacja głównych wątków
4. **Etap 2 - qwen-coder**: Przetworzenie struktury, formatowanie, generowanie metadanych
5. **Etap 3 - qwen3.6-35B-A3B**: Głęboka analiza treści, przepisanie tekstu z zachowaniem stylu i znaczenia

### Struktura chunków

Każdy chunk zawiera metadane JSON z następującymi informacjami:

```json
{
  "chunk_id": "unikalny_identifikator_chunka",
  "token_count": 4096,
  "previous_chunk": "ID poprzedniego chunka lub null",
  "next_chunk": "ID następnego chunka lub null",
  "previous_subsection": "ID poprzedniego podrozdziału lub null",
  "next_subsection": "ID następnego podrozdziału lub null",
  "subsection": "ID bieżącego podrozdziału",
  "chapter": "ID rozdziału",
  "book_summary": "Streszczenie całej książki",
  "all_books_summary": "Streszczenie wszystkich książek z katalogu /input",
  "content": "Przetworzony tekst chunka"
}
```

Struktura katalogów po przetworzeniu:

```
/workspace/
├── input/              # Pliki wejściowe (książki)
├── tmp/                # Pliki tymczasowe (.txt po konwersji)
├── chunk/              # Chunki po 4096 tokenów z metadanymi JSON
├── output/             # Finalne wyniki
├── logs/               # Logi procesu
└── temp/               # Dodatkowe pliki robocze
```

## Przykładowy przepływ

```bash
# 1. Wczytanie książki
cat input/book.txt | \
# 2. Przetworzenie przez agenta
./step1_agent.sh | \
# 3. Przetworzenie przez codera
./step2_coder.sh | \
# 4. Finalne przepisanie
./step3_rewriter.sh > output/book_rewritten.txt
```

## Logowanie i Debugowanie

Logi są zapisywane w katalogu `logs/`:
- `pipeline.log` - Ogólne logi procesu
- `agent.log` - Logi z qwen-agent
- `coder.log` - Logi z qwen-coder
- `rewriter.log` - Logi z qwen3.6-35B-A3B

Aby włączyć debugowanie:
```bash
export DEBUG=1
./pipeline.sh input/book.txt output/result.txt
```

## Rozwiązywanie problemów

### Problem: Brak odpowiedzi od API
- Sprawdź połączenie sieciowe
- Zweryfikuj klucze API w config.sh
- Sprawdź limity rate-limiting

### Problem: Ucięty output
- Zwiększ `MAX_TOKENS` w konfiguracji
- Podziel tekst na mniejsze segmenty

### Problem: Niska jakość przetwarzania
- Dostosuj parametr `TEMPERATURE`
- Sprawdź prompt engineering w skryptach

## Bezpieczeństwo

- **Nigdy nie commituj** pliku `config.sh` z prawdziwymi kluczami API
- Dodaj `config.sh` do `.gitignore`
- Używaj zmiennych środowiskowych dla wrażliwych danych

## Licencja

MIT License - zobacz plik [LICENSE](LICENSE)

## Wkład w projekt

1. Fork repozytorium
2. Utwórz branch (`git checkout -b feature/nowa-funkcjonalnosc`)
3. Commit zmian (`git commit -m 'Dodano nową funkcjonalność'`)
4. Push (`git push origin feature/nowa-funkcjonalnosc`)
5. Otwórz Pull Request

## Kontakt i Wsparcie

W przypadku pytań i problemów proszę otworzyć issue w repozytorium.

---

**Uwaga**: Ten projekt wykorzystuje modele AI firmy Alibaba Cloud (Qwen). Upewnij się, że masz odpowiednie uprawnienia i klucze API przed użyciem.