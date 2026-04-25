#!/bin/bash

# Skrypt do konwersji plików z katalogu /input na format .txt do katalogu /tmp
# Obsługuje różne formaty plików (doc, docx, pdf, rtf, odt)

set -e

# Domyślne wartości
INPUT_DIR="/input"
OUTPUT_DIR="/tmp"
VERBOSE=false
FORCE=false
FORMAT=""

# Funkcja wyświetlająca pomoc
show_help() {
    cat << EOF
Skrypt do konwersji plików na format .txt

Użycie: $(basename "$0") [OPCJE]

OPCJE:
    -i, --input DIR       Katalog wejściowy z plikami do konwersji (domyślnie: /input)
    -o, --output DIR      Katalog wyjściowy dla plików .txt (domyślnie: /tmp)
    -f, --format FORMAT   Format plików do konwersji (doc, docx, pdf, rtf, odt, all)
    -v, --verbose         Tryb szczegółowy - wyświetla dodatkowe informacje
    -F, --force           Nadpisz istniejące pliki wyjściowe
    -h, --help            Wyświetl tę pomoc i zakończ

PRZYKŁADY:
    $(basename "$0") -i /moje/pliki -o /wyniki
    $(basename "$0") -f pdf -v
    $(basename "$0") --input /docs --output /text --format docx --verbose

EOF
    exit 0
}

# Funkcja logująca
log() {
    if [ "$VERBOSE" = true ]; then
        echo "[INFO] $1"
    fi
}

log_error() {
    echo "[BŁĄD] $1" >&2
}

log_warn() {
    echo "[OSTRZEŻENIE] $1" >&2
}

# Parsowanie argumentów wiersza poleceń
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--input)
            INPUT_DIR="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -f|--format)
            FORMAT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -F|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            log_error "Nieznana opcja: $1"
            echo "Użyj '$(basename "$0") --help' aby uzyskać więcej informacji." >&2
            exit 1
            ;;
    esac
done

# Walidacja katalogu wejściowego
if [ ! -d "$INPUT_DIR" ]; then
    log_error "Katalog wejściowy nie istnieje: $INPUT_DIR"
    exit 1
fi

# Tworzenie katalogu wyjściowego jeśli nie istnieje
if [ ! -d "$OUTPUT_DIR" ]; then
    log "Tworzenie katalogu wyjściowego: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
fi

# Sprawdzenie dostępności narzędzi do konwersji
check_dependencies() {
    local missing_tools=()
    
    # Sprawdź pandoc (do konwersji dokumentów)
    if ! command -v pandoc &> /dev/null; then
        missing_tools+=("pandoc")
    fi
    
    # Sprawdź pdftotext (do PDF)
    if ! command -v pdftotext &> /dev/null; then
        missing_tools+=("pdftotext")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_warn "Brakujące narzędzia: ${missing_tools[*]}"
        log_warn "Konwersja może być ograniczona. Instaluj: apt-get install pandoc poppler-utils"
    fi
    
    return 0
}

# Funkcja konwertująca pojedynczy plik
convert_file() {
    local input_file="$1"
    local filename=$(basename "$input_file")
    local name_without_ext="${filename%.*}"
    local extension="${filename##*.}"
    local output_file="$OUTPUT_DIR/${name_without_ext}.txt"
    
    # Sprawdź czy plik wyjściowy już istnieje
    if [ -f "$output_file" ] && [ "$FORCE" = false ]; then
        log_warn "Plik już istnieje, pomijam: $output_file (użyj --force aby nadpisać)"
        return 0
    fi
    
    log "Konwertowanie: $filename -> ${name_without_ext}.txt"
    
    # Konwersja w zależności od formatu
    case "$extension" in
        txt)
            # Jeśli to już txt, po prostu kopiuj
            cp "$input_file" "$output_file"
            ;;
        pdf)
            if command -v pdftotext &> /dev/null; then
                pdftotext "$input_file" "$output_file"
            else
                log_error "Brak narzędzia pdftotext do konwersji PDF"
                return 1
            fi
            ;;
        doc|docx|rtf|odt|html|md|markdown)
            if command -v pandoc &> /dev/null; then
                pandoc -f "${extension}" -t plain -o "$output_file" "$input_file" 2>/dev/null || \
                pandoc -t plain -o "$output_file" "$input_file"
            else
                log_error "Brak narzędzia pandoc do konwersji dokumentów"
                return 1
            fi
            ;;
        *)
            log_warn "Nieobsługiwany format: $extension, próba konwersji przez pandoc"
            if command -v pandoc &> /dev/null; then
                pandoc -t plain -o "$output_file" "$input_file" 2>/dev/null || {
                    log_error "Nie udało się przekonwertować: $filename"
                    return 1
                }
            else
                log_error "Brak narzędzia do konwersji formatu: $extension"
                return 1
            fi
            ;;
    esac
    
    if [ -f "$output_file" ]; then
        log "Sukces: $output_file"
        return 0
    else
        log_error "Konwersja nie powiodła się: $filename"
        return 1
    fi
}

# Główna funkcja
main() {
    log "Katalog wejściowy: $INPUT_DIR"
    log "Katalog wyjściowy: $OUTPUT_DIR"
    log "Tryb szczegółowy: $VERBOSE"
    log "Nadpisywanie: $FORCE"
    
    # Sprawdź zależności
    check_dependencies
    
    # Znajdź pliki do konwersji
    local files_converted=0
    local files_failed=0
    
    # Określ jakie rozszerzenia przetwarzać
    local extensions=()
    if [ -z "$FORMAT" ] || [ "$FORMAT" = "all" ]; then
        extensions=("txt" "pdf" "doc" "docx" "rtf" "odt" "html" "md" "markdown")
    else
        extensions=("$FORMAT")
    fi
    
    log "Przetwarzane formaty: ${extensions[*]}"
    
    # Przetwarzaj każdy plik
    for ext in "${extensions[@]}"; do
        shopt -s nullglob nocaseglob
        for file in "$INPUT_DIR"/*."$ext"; do
            if [ -f "$file" ]; then
                if convert_file "$file"; then
                    files_converted=$((files_converted + 1))
                else
                    files_failed=$((files_failed + 1))
                fi
            fi
        done
        shopt -u nullglob nocaseglob
    done
    
    # Podsumowanie
    echo ""
    echo "=== PODSUMOWANIE ==="
    echo "Przekonwertowano plików: $files_converted"
    echo "Nieudane konwersje: $files_failed"
    echo "Pliki wyjściowe: $OUTPUT_DIR"
    
    if [ $files_failed -gt 0 ]; then
        exit 1
    fi
}

# Uruchom główną funkcję
main
