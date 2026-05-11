#!/bin/bash
#
# Skrypt do wysyłki plików do Moodle przez Web Services API
# Używany przez full_workflow.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"
FINISH_DIR="$SCRIPT_DIR/finish"

# Kolory
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
DRY_RUN=false

# Parsowanie argumentów
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose) VERBOSE=true; shift ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Użycie: $0 [-v] [-n] [-h]"
            echo "  -v  Tryb szczegółowy"
            echo "  -n  Dry run (nie wysyłaj, tylko pokaż co by zostało wysłane)"
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
    local file_size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null)
    
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Wysyłanie: $filename ($file_size bytes)"
        return 0
    fi
    
    # Przygotowanie danych do API
    local response=$(curl -s -X POST "$MOODLE_URL/webservice/rest/server.php" \
        -H "Content-Type: application/x-www-form-urlencoded" \
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
        echo "Odpowiedź: $response"
        return 1
    fi
}

# Dodanie pliku do sekcji kursu (opcjonalne)
add_file_to_course_section() {
    local file_id="$1"
    local filename="$2"
    
    log "Dodawanie pliku do sekcji kursu..."
    
    # To zależy od wersji Moodle i dostępnych web services
    # Przykładowe użycie core_course_add_contents_item
    
    curl -s -X POST "$MOODLE_URL/webservice/rest/server.php" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "wstoken=$MOODLE_TOKEN" \
        -d "wsfunction=core_course_add_contents_item" \
        -d "moodlewsrestformat=json" \
        -d "courseid=$MOODLE_COURSE_ID" \
        -d "section=$MOODLE_SECTION_ID" \
        -d "module=file" \
        -d "name=$filename" \
        -d "contents[0][type]=file" \
        -d "contents[0][file]=$file_id" \
        >/dev/null 2>&1 || true
    
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
    
    echo -e "${BLUE}Konfiguracja:${NC}"
    echo "  Moodle URL: $MOODLE_URL"
    echo "  Course ID: $MOODLE_COURSE_ID"
    if [[ -n "$MOODLE_SECTION_ID" ]]; then
        echo "  Section ID: $MOODLE_SECTION_ID"
    fi
    echo ""
    echo -e "${BLUE}Znaleziono plików:${NC} ${#files[@]}"
    echo ""
    
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}=== TRYB DRY RUN - Pliki nie zostaną wysłane ===${NC}"
        echo ""
    fi
    
    local success=0
    local failed=0
    
    for file in "${files[@]}"; do
        if [[ -f "$file" ]]; then
            local filesize=$(du -h "$file" | cut -f1)
            echo -n "  $(basename "$file") ($filesize)... "
            
            if upload_file_to_moodle "$file"; then
                echo -e "${GREEN}OK${NC}"
                ((success++)) || true
            else
                echo -e "${RED}BŁĄD${NC}"
                ((failed++)) || true
            fi
        fi
    done
    
    echo ""
    echo "=========================================="
    echo "Podsumowanie:"
    echo -e "  ${GREEN}Sukces: $success${NC}"
    echo -e "  ${RED}Błędy: $failed${NC}"
    echo "=========================================="
    
    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
    
    exit 0
}

main "$@"
