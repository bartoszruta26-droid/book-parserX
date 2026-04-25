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
├── output/             # Katalog z przetworzonymi wynikami
├── logs/               # Logi z procesu przetwarzania
└── temp/               # Pliki tymczasowe
```

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone <repository-url>
cd book-parserX
```

2. Utwórz niezbędne katalogi:
```bash
mkdir -p input output logs temp
```

3. Skonfiguruj zmienne środowiskowe w `config.sh`:
```bash
cp config.sh.example config.sh
# Edytuj config.sh i dodaj swoje klucze API
```

## Użycie

### Podstawowe uruchomienie

```bash
./pipeline.sh input/moja_ksiazka.txt output/przetworzona_ksiazka.txt
```

### Tryb szczegółowy (z logowaniem)

```bash
./pipeline.sh -v input/moja_ksiazka.txt output/wynik.txt
```

### Przetwarzanie całego katalogu

```bash
for file in input/*.txt; do
    ./pipeline.sh "$file" "output/processed_$(basename $file)"
done
```

## Konfiguracja

Edytuj plik `config.sh`, aby ustawić:

- `QWEN_API_KEY` - Twój klucz API
- `QWEN_AGENT_URL` - Endpoint dla qwen-agent
- `QWEN_CODER_URL` - Endpoint dla qwen-coder
- `QWEN_LARGE_MODEL_URL` - Endpoint dla qwen3.6-35B-A3B
- `MAX_TOKENS` - Maksymalna liczba tokenów na żądanie
- `TEMPERATURE` - Parametr kreatywności modelu

## Jak działa Pipeline?

1. **Etap 1 - qwen-agent**: Analiza struktury książki, podział na rozdziały, identyfikacja głównych wątków
2. **Etap 2 - qwen-coder**: Przetworzenie struktury, formatowanie, generowanie metadanych
3. **Etap 3 - qwen3.6-35B-A3B**: Głęboka analiza treści, przepisanie tekstu z zachowaniem stylu i znaczenia

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