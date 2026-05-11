#!/bin/bash
#
# Kompletny workflow: Konwersja -> Chunking -> Przepisywanie -> Moodle Upload
# Uruchamia cały proces jedną komendą
#
# Użycie: ./full_workflow.sh [opcje]
#

set -e

# Ścieżki
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Zmienne
VERBOSE=false
SKIP_CONVERSION=false
SKIP_CHUNKING=false
SKIP_REWRITE=false
SKIP_MOODLE=false
MOODLE_ONLY=false

# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     KOMPLETNY WORKFLOW - BOOK TO MOODLE PIPELINE            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}➜${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

show_help() {
    cat << EOF
Kompletny workflow przetwarzania książek i wysyłki do Moodle

Użycie: $(basename "$0") [OPCJE]

OPCJE:
    -v, --verbose         Tryb szczegółowy
    -c, --skip-conversion Pominięcie konwersji (zakłada gotowe .txt)
    -u, --skip-chunking   Pominięcie chunkingu
    -r, --skip-rewrite    Pominięcie przepisywania AI
    -m, --skip-moodle     Pominięcie wysyłki do Moodle
    -o, --moodle-only     Tylko wysyłka do Moodle (z /finish)
    -h, --help            Wyświetl pomoc

PRZYKŁADY:
    $(basename "$0")                      # Pełny workflow
    $(basename "$0") -v                   # Ze szczegółowym logowaniem
    $(basename "$0") --skip-rewrite       # Bez przepisywania AI
    $(basename "$0") --moodle-only        # Tylko upload do Moodle

EOF
    exit 0
}

# Parsowanie argumentów
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--skip-conversion)
            SKIP_CONVERSION=true
            shift
            ;;
        -u|--skip-chunking)
            SKIP_CHUNKING=true
            shift
            ;;
        -r|--skip-rewrite)
            SKIP_REWRITE=true
            shift
            ;;
        -m|--skip-moodle)
            SKIP_MOODLE=true
            shift
            ;;
        -o|--moodle-only)
            MOODLE_ONLY=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            print_error "Nieznana opcja: $1"
            echo "Użyj '$(basename "$0") --help' aby uzyskać więcej informacji." >&2
            exit 1
            ;;
    esac
done

# ============================================================================
# ŁADOWANIE KONFIGURACJI
# ============================================================================

load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        print_success "Załadowano konfigurację z $CONFIG_FILE"
        return 0
    else
        print_warning "Plik konfiguracyjny nie istnieje: $CONFIG_FILE"
        print_warning "Uruchom najpierw: ./install.sh --configure"
        return 1
    fi
}

check_moodle_config() {
    if [[ -z "$MOODLE_URL" ]] || [[ -z "$MOODLE_TOKEN" ]] || [[ -z "$MOODLE_COURSE_ID" ]]; then
        print_error "Brak konfiguracji Moodle w config.sh"
        print_error "Wymagane zmienne: MOODLE_URL, MOODLE_TOKEN, MOODLE_COURSE_ID"
        return 1
    fi
    print_success "Konfiguracja Moodle poprawna"
    return 0
}

# ============================================================================
# ETAP 1: KONWERSJA PLIKÓW DO TXT
# ============================================================================

run_conversion() {
    if [[ "$SKIP_CONVERSION" == true ]]; then
        print_warning "Pominięto konwersję (--skip-conversion)"
        return 0
    fi
    
    print_header
    print_step "ETAP 1/4: Konwersja plików do formatu TXT"
    echo ""
    
    if [[ ! -x "$SCRIPT_DIR/convert_to_txt.sh" ]]; then
        print_error "Skrypt convert_to_txt.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        "$SCRIPT_DIR/convert_to_txt.sh" -v
    else
        "$SCRIPT_DIR/convert_to_txt.sh"
    fi
    
    local result=$?
    if [[ $result -eq 0 ]]; then
        print_success "Konwersja zakończona sukcesem"
    else
        print_error "Konwersja zakończona błędem"
        return 1
    fi
    
    echo ""
    return 0
}

# ============================================================================
# ETAP 2: CHUNKING
# ============================================================================

run_chunking() {
    if [[ "$SKIP_CHUNKING" == true ]]; then
        print_warning "Pominięto chunking (--skip-chunking)"
        return 0
    fi
    
    print_step "ETAP 2/4: Dzielenie na chunki"
    echo ""
    
    if [[ ! -x "$SCRIPT_DIR/chunk_script.sh" ]]; then
        print_error "Skrypt chunk_script.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    # Sprawdź czy są pliki do przetworzenia w tmp
    local txt_files=$(find "$SCRIPT_DIR/tmp" -name "*.txt" -type f 2>/dev/null | wc -l)
    if [[ $txt_files -eq 0 ]]; then
        print_warning "Brak plików .txt w katalogu tmp/"
        print_warning "Najpierw uruchom konwersję lub użyj --skip-conversion"
        return 1
    fi
    
    print_success "Znaleziono $txt_files plik(ów) do podziału"
    
    # Proces każdego pliku
    for txt_file in "$SCRIPT_DIR/tmp"/*.txt; do
        if [[ -f "$txt_file" ]]; then
            echo "Przetwarzanie: $(basename "$txt_file")"
            "$SCRIPT_DIR/chunk_script.sh" -o "$SCRIPT_DIR/chunk" "$txt_file"
        fi
    done
    
    local chunk_count=$(find "$SCRIPT_DIR/chunk" -name "*_chunk_*.txt" -type f 2>/dev/null | wc -l)
    print_success "Utworzono $chunk_count chunków"
    echo ""
    return 0
}

# ============================================================================
# ETAP 3: PRZEPISYWANIE AI
# ============================================================================

run_rewrite() {
    if [[ "$SKIP_REWRITE" == true ]]; then
        print_warning "Pominięto przepisywanie AI (--skip-rewrite)"
        return 0
    fi
    
    print_step "ETAP 3/4: Przepisywanie chunków przez AI"
    echo ""
    
    if [[ ! -x "$SCRIPT_DIR/rewrite_chunks.sh" ]]; then
        print_error "Skrypt rewrite_chunks.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    # Sprawdź konfigurację API
    if [[ -z "$QWEN_API_KEY" ]]; then
        print_warning "Brak klucza API Qwen - przepisywanie może nie działać"
        read -p "Czy kontynuować? (t/n): " confirm
        if [[ "$confirm" != "t" ]] && [[ "$confirm" != "T" ]]; then
            return 1
        fi
    fi
    
    local chunk_count=$(find "$SCRIPT_DIR/chunk" -name "*_chunk_*.txt" -type f 2>/dev/null | wc -l)
    if [[ $chunk_count -eq 0 ]]; then
        print_warning "Brak chunków do przetworzenia"
        return 1
    fi
    
    print_success "Przetwarzanie $chunk_count chunków..."
    
    if [[ "$VERBOSE" == true ]]; then
        "$SCRIPT_DIR/rewrite_chunks.sh"
    else
        "$SCRIPT_DIR/rewrite_chunks.sh" 2>&1
    fi
    
    local result=$?
    if [[ $result -eq 0 ]]; then
        local output_count=$(find "$SCRIPT_DIR/output" -name "*_rewritten.json" -type f 2>/dev/null | wc -l)
        print_success "Przepisywanie zakończone: $output_count plików"
    else
        print_error "Przepisywanie zakończone błędem"
        return 1
    fi
    
    echo ""
    return 0
}

# ============================================================================
# ETAP 4: SKŁADANIE I WYSYŁKA DO MOODLE
# ============================================================================

assemble_and_upload() {
    if [[ "$MOODLE_ONLY" == true ]]; then
        print_step "ETAP 4/4: Wysyłka do Moodle (tryb tylko Moodle)"
    elif [[ "$SKIP_MOODLE" == true ]]; then
        print_warning "Pominięto wysyłkę do Moodle (--skip-moodle)"
        
        # Samo składanie książki
        print_step "Składanie książki z chunków..."
        assemble_book_only
        return $?
    else
        print_step "ETAP 4/4: Składanie książki i wysyłka do Moodle"
    fi
    
    echo ""
    
    # Sprawdzenie output
    if [[ ! -d "$SCRIPT_DIR/output" ]] || [[ -z "$(ls -A "$SCRIPT_DIR/output" 2>/dev/null)" ]]; then
        print_error "Brak przetworzonych chunków w output/"
        return 1
    fi
    
    # Stwórz skrypt upload jeśli nie istnieje
    if [[ ! -x "$SCRIPT_DIR/upload_to_moodle.sh" ]]; then
        print_warning "Skrypt upload_to_moodle.sh nie istnieje"
        print_warning "Tworzenie podstawowego skryptu upload..."
        create_moodle_upload_script
    fi
    
    # Najpierw złóż książkę
    if [[ "$MOODLE_ONLY" != true ]]; then
        assemble_book_only
    fi
    
    # Upload do Moodle
    print_success "Rozpoczynanie wysyłki do Moodle..."
    
    if [[ "$VERBOSE" == true ]]; then
        "$SCRIPT_DIR/upload_to_moodle.sh" -v
    else
        "$SCRIPT_DIR/upload_to_moodle.sh"
    fi
    
    local result=$?
    if [[ $result -eq 0 ]]; then
        print_success "Wysyłka do Moodle zakończona sukcesem!"
    else
        print_error "Wysyłka do Moodle zakończona błędem"
        return 1
    fi
    
    echo ""
    return 0
}

assemble_book_only() {
    mkdir -p "$SCRIPT_DIR/finish"
    
    local book_name="book_$(date +%Y%m%d_%H%M%S)"
    local final_file="$SCRIPT_DIR/finish/${book_name}.txt"
    local temp_merged="$SCRIPT_DIR/temp/merged_book.txt"
    
    mkdir -p "$SCRIPT_DIR/temp"
    > "$temp_merged"
    
    local chunk_count=0
    for chunk_file in "$SCRIPT_DIR/output"/*_rewritten.json; do
        if [[ -f "$chunk_file" ]]; then
            if command -v jq >/dev/null 2>&1; then
                jq -r '.content // empty' "$chunk_file" >> "$temp_merged"
                echo "" >> "$temp_merged"
                ((chunk_count++)) || true
            fi
        fi
    done
    
    if [[ $chunk_count -eq 0 ]]; then
        print_error "Nie znaleziono przetworzonych chunków"
        return 1
    fi
    
    mv "$temp_merged" "$final_file"
    
    print_success "Książka złożona: $final_file"
    print_success "Liczba chunków: $chunk_count"
    return 0
}

create_moodle_upload_script() {
    cat > "$SCRIPT_DIR/upload_to_moodle.sh" << 'MOODLE_SCRIPT'
#!/bin/bash
#
# Skrypt do wysyłki plików do Moodle przez Web Services API
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"
FINISH_DIR="$SCRIPT_DIR/finish"

# Kolory
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Ładowanie konfiguracji
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo -e "${RED}Błąd: Brak pliku konfiguracyjnego $CONFIG_FILE${NC}"
    exit 1
fi

# Walidacja konfiguracji Moodle
if [[ -z "$MOODLE_URL" ]] || [[ -z "$MOODLE_TOKEN" ]] || [[ -z "$MOODLE_COURSE_ID" ]]; then
    echo -e "${RED}Błąd: Brak wymaganych zmiennych Moodle w config.sh${NC}"
    echo "Wymagane: MOODLE_URL, MOODLE_TOKEN, MOODLE_COURSE_ID"
    exit 1
fi

VERBOSE=false

# Parsowanie argumentów
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose) VERBOSE=true; shift ;;
        -h|--help)
            echo "Użycie: $0 [-v] [-h]"
            echo "  -v  Tryb szczegółowy"
            echo "  -h  Pomoc"
            exit 0
            ;;
        *) shift ;;
    esac
done

log() {
    if [[ "$VERBOSE" == true ]]; then
        echo -e "${GREEN}[INFO]${NC} $1"
    fi
}

# Funkcja wysyłająca plik do Moodle
upload_file_to_moodle() {
    local file_path="$1"
    local filename=$(basename "$file_path")
    
    log "Wysyłanie pliku: $filename"
    
    # Encode pliku do base64
    local file_content_base64=$(base64 -w 0 "$file_path")
    local file_size=$(stat -f%z "$file_path" 2>/dev/null || stat -c%s "$file_path" 2>/dev/null)
    
    # Przygotowanie danych do API
    local response=$(curl -s -X POST "$MOODLE_URL/webservice/rest/server.php" \
        -d "wstoken=$MOODLE_TOKEN" \
        -d "wsfunction=core_user_upload_private_file" \
        -d "moodlewsrestformat=json" \
        -d "itemid=0" \
        -d "filename=$filename" \
        -d "filepath=/" \
        -d "filecontent=$file_content_base64" \
        -d "contextid=")
    
    # Sprawdzenie odpowiedzi
    if echo "$response" | grep -q "exception"; then
        echo -e "${RED}Błąd podczas wysyłki: $response${NC}"
        return 1
    fi
    
    # Ekstrakcja ID pliku
    local file_id=$(echo "$response" | grep -o '"id":[0-9]*' | cut -d':' -f2)
    
    if [[ -n "$file_id" ]]; then
        log "Plik przesłany pomyślnie, ID: $file_id"
        
        # Jeśli MOODLE_SECTION_ID jest ustawione, dodaj plik do sekcji kursu
        if [[ -n "$MOODLE_SECTION_ID" ]]; then
            add_file_to_course_section "$file_id" "$filename"
        fi
        
        return 0
    else
        echo -e "${RED}Nie udało się uzyskać ID pliku${NC}"
        return 1
    fi
}

# Dodanie pliku do sekcji kursu (opcjonalne)
add_file_to_course_section() {
    local file_id="$1"
    local filename="$2"
    
    log "Dodawanie pliku do sekcji kursu..."
    
    # Użycie core_course_add_contents_item lub podobnej funkcji
    # To zależy od wersji Moodle i dostępnych web services
    
    curl -s -X POST "$MOODLE_URL/webservice/rest/server.php" \
        -d "wstoken=$MOODLE_TOKEN" \
        -d "wsfunction=core_course_update_module" \
        -d "moodlewsrestformat=json" \
        -d "courseid=$MOODLE_COURSE_ID" \
        -d "sectionid=$MOODLE_SECTION_ID" \
        -d "name=$filename" \
        -d "files[]=$file_id" \
        >/dev/null
    
    log "Plik dodany do sekcji kursu"
}

# Główna funkcja
main() {
    echo "=========================================="
    echo "  Wysyłka plików do Moodle"
    echo "=========================================="
    echo ""
    
    # Sprawdź katalog finish
    if [[ ! -d "$FINISH_DIR" ]]; then
        echo -e "${RED}Błąd: Katalog $FINISH_DIR nie istnieje${NC}"
        exit 1
    fi
    
    local files=( "$FINISH_DIR"/*.txt )
    if [[ ! -e "${files[0]}" ]]; then
        echo -e "${RED}Błąd: Brak plików .txt w $FINISH_DIR${NC}"
        exit 1
    fi
    
    echo "Moodle URL: $MOODLE_URL"
    echo "Course ID: $MOODLE_COURSE_ID"
    echo "Znaleziono plików: ${#files[@]}"
    echo ""
    
    local success=0
    local failed=0
    
    for file in "${files[@]}"; do
        if [[ -f "$file" ]]; then
            if upload_file_to_moodle "$file"; then
                ((success++)) || true
            else
                ((failed++)) || true
            fi
        fi
    done
    
    echo ""
    echo "=========================================="
    echo "Podsumowanie:"
    echo "  Sukces: $success"
    echo "  Błędy: $failed"
    echo "=========================================="
    
    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
    
    exit 0
}

main "$@"
MOODLE_SCRIPT

    chmod +x "$SCRIPT_DIR/upload_to_moodle.sh"
    print_success "Utworzono skrypt upload_to_moodle.sh"
}

# ============================================================================
# GŁÓWNA FUNKCJA
# ============================================================================

main() {
    print_header
    
    # Load configuration
    if ! load_config; then
        print_warning "Kontynuacja bez pełnej konfiguracji..."
    fi
    
    # Check Moodle config if needed
    if [[ "$SKIP_MOODLE" != true ]] || [[ "$MOODLE_ONLY" == true ]]; then
        if ! check_moodle_config; then
            print_warning "Wysyłka do Moodle zostanie pominięta"
            SKIP_MOODLE=true
        fi
    fi
    
    local start_time=$(date +%s)
    
    # Execute pipeline
    if [[ "$MOODLE_ONLY" == true ]]; then
        assemble_and_upload
    else
        run_conversion && \
        run_chunking && \
        run_rewrite && \
        assemble_and_upload
    fi
    
    local result=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo ""
    echo "=========================================="
    if [[ $result -eq 0 ]]; then
        print_success "WORKFLOW ZAKOŃCZONY SUKCESEM!"
    else
        print_error "WORKFLOW ZAKOŃCZONY BŁĘDEM"
    fi
    echo "Czas trwania: ${duration}s"
    echo "=========================================="
    
    return $result
}

# Run main function
main "$@"
