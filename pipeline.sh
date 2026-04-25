#!/bin/bash
#
# Book Rewriting Pipeline - Terminal User Interface (TUI)
# Skrypt główny z interfejsem tekstowym do obsługi aplikacji
#
# Użycie: ./pipeline.sh [tryb] [opcje]
#

set -e

# Ścieżki do katalogów
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT_DIR="$SCRIPT_DIR/input"
TMP_DIR="$SCRIPT_DIR/tmp"
CHUNK_DIR="$SCRIPT_DIR/chunk"
OUTPUT_DIR="$SCRIPT_DIR/output"
LOGS_DIR="$SCRIPT_DIR/logs"
TEMP_DIR="$SCRIPT_DIR/temp"

# Plik konfiguracyjny
CONFIG_FILE="$SCRIPT_DIR/config.sh"

# Kolory dla TUI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color
BOLD='\033[1m'
DIM='\033[2m'

# Zmienne globalne
VERBOSE=false
DEBUG=false
CURRENT_MENU="main"
SELECTED_FILE=""
PROCESSING_STATUS="idle"

# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    if [[ "$VERBOSE" == true ]] || [[ "$level" != "DEBUG" ]]; then
        echo -e "${DIM}[$timestamp]${NC} ${BOLD}[$level]${NC} $message"
    fi
    
    if [[ -d "$LOGS_DIR" ]]; then
        echo "[$timestamp] [$level] $message" >> "$LOGS_DIR/pipeline.log"
    fi
}

print_color() {
    local color="$1"
    shift
    echo -e "${color}$*${NC}"
}

print_header() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           BOOK REWRITING PIPELINE - TUI                      ║"
    echo "║           System przepisywania książek z AI                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_menu_header() {
    local title="$1"
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC} ${BOLD}$title${NC}"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"
    echo ""
}

print_option() {
    local key="$1"
    local description="$2"
    local extra="${3:-}"
    echo -e "  ${GREEN}$key${NC}) $description $extra"
}

print_separator() {
    echo -e "${DIM}─────────────────────────────────────────────────────────────${NC}"
}

wait_for_key() {
    local message="${1:-Naciśnij Enter, aby kontynuować...}"
    echo ""
    read -p "$message" -n 1 -s
    echo ""
}

clear_screen() {
    clear
}

# ============================================================================
# FUNKCJE INFRASTRUKTURY
# ============================================================================

init_directories() {
    log "INFO" "Inicjalizacja katalogów..."
    mkdir -p "$INPUT_DIR" "$TMP_DIR" "$CHUNK_DIR" "$OUTPUT_DIR" "$LOGS_DIR" "$TEMP_DIR"
    print_color $GREEN "✓ Katalogi zostały utworzone"
}

check_dependencies() {
    log "INFO" "Sprawdzanie zależności..."
    local missing=()
    
    command -v curl >/dev/null 2>&1 || missing+=("curl")
    command -v jq >/dev/null 2>&1 || missing+=("jq")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        print_color $YELLOW "⚠ Brakujące narzędzia: ${missing[*]}"
        print_color $YELLOW "  Zainstaluj: apt-get install ${missing[*]}"
        return 1
    else
        print_color $GREEN "✓ Wszystkie zależności są dostępne"
        return 0
    fi
}

load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        log "DEBUG" "Załadowano konfigurację z $CONFIG_FILE"
        return 0
    else
        log "WARN" "Plik konfiguracyjny nie istnieje: $CONFIG_FILE"
        return 1
    fi
}

# ============================================================================
# FUNKCJE PRZETWARZANIA
# ============================================================================

list_input_files() {
    echo ""
    print_menu_header "Pliki w katalogu input"
    
    if [[ ! -d "$INPUT_DIR" ]] || [[ -z "$(ls -A "$INPUT_DIR" 2>/dev/null)" ]]; then
        print_color $YELLOW "  Brak plików w katalogu $INPUT_DIR"
        return 1
    fi
    
    local count=0
    for file in "$INPUT_DIR"/*; do
        if [[ -f "$file" ]]; then
            ((count++))
            local filename=$(basename "$file")
            local size=$(du -h "$file" | cut -f1)
            echo -e "  ${WHITE}$count.${NC} $filename ${DIM}($size)${NC}"
        fi
    done
    
    if [[ $count -eq 0 ]]; then
        print_color $YELLOW "  Brak plików do przetworzenia"
        return 1
    fi
    
    echo ""
    echo -e "  Razem: ${GREEN}$count${NC} plik(ów)"
    return 0
}

select_input_file() {
    SELECTED_FILE=""
    
    if [[ ! -d "$INPUT_DIR" ]] || [[ -z "$(ls -A "$INPUT_DIR" 2>/dev/null)" ]]; then
        print_color $YELLOW "Brak plików w katalogu input"
        return 1
    fi
    
    local files=()
    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find "$INPUT_DIR" -maxdepth 1 -type f -print0 2>/dev/null)
    
    if [[ ${#files[@]} -eq 0 ]]; then
        print_color $YELLOW "Brak plików do wyboru"
        return 1
    fi
    
    echo ""
    print_menu_header "Wybierz plik do przetworzenia"
    
    for i in "${!files[@]}"; do
        local filename=$(basename "${files[$i]}")
        local size=$(du -h "${files[$i]}" | cut -f1)
        echo -e "  ${GREEN}$((i+1))${NC}) $filename ${DIM}($size)${NC}"
    done
    
    echo -e "  ${GREEN}0${NC}) Powrót"
    echo ""
    
    while true; do
        read -p "  Wybierz numer (0-${#files[@]}): " choice
        
        if [[ "$choice" == "0" ]]; then
            return 1
        elif [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le "${#files[@]}" ]]; then
            SELECTED_FILE="${files[$((choice-1))]}"
            print_color $GREEN "  ✓ Wybrano: $(basename "$SELECTED_FILE")"
            return 0
        else
            print_color $RED "  Nieprawidłowy wybór"
        fi
    done
}

run_conversion() {
    print_menu_header "Konwersja plików do TXT"
    
    if [[ ! -x "$SCRIPT_DIR/convert_to_txt.sh" ]]; then
        print_color $RED "Skrypt convert_to_txt.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    echo "Rozpoczynanie konwersji..."
    echo ""
    
    if [[ "$VERBOSE" == true ]]; then
        "$SCRIPT_DIR/convert_to_txt.sh" -v
    else
        "$SCRIPT_DIR/convert_to_txt.sh"
    fi
    
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        print_color $GREEN "✓ Konwersja zakończona sukcesem"
    else
        print_color $RED "✗ Konwersja zakończona błędem"
    fi
    
    wait_for_key
    return $result
}

run_chunking() {
    print_menu_header "Dzielenie na chunki"
    
    if [[ ! -x "$SCRIPT_DIR/chunk_script.sh" ]]; then
        print_color $RED "Skrypt chunk_script.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    list_input_files
    
    if [[ -z "$SELECTED_FILE" ]]; then
        select_input_file || return 1
    fi
    
    local tmp_file="$TMP_DIR/$(basename "$SELECTED_FILE" | sed 's/\.[^.]*$//').txt"
    
    if [[ ! -f "$tmp_file" ]]; then
        print_color $YELLOW "Plik tymczasowy nie istnieje: $tmp_file"
        print_color $YELLOW "Najpierw uruchom konwersję"
        wait_for_key
        return 1
    fi
    
    echo ""
    echo "Przetwarzanie: $(basename "$tmp_file")"
    echo ""
    
    "$SCRIPT_DIR/chunk_script.sh" -o "$CHUNK_DIR" "$tmp_file"
    
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        print_color $GREEN "✓ Chunking zakończony sukcesem"
    else
        print_color $RED "✗ Chunking zakończony błędem"
    fi
    
    wait_for_key
    return $result
}

run_rewrite() {
    print_menu_header "Przepisywanie chunków"
    
    if [[ ! -x "$SCRIPT_DIR/rewrite_chunks.sh" ]]; then
        print_color $RED "Skrypt rewrite_chunks.sh nie istnieje lub nie jest wykonywalny"
        return 1
    fi
    
    echo "Sprawdzanie chunków..."
    local chunk_count=$(find "$CHUNK_DIR" -type f -name "*.txt" -o -name "*.json" 2>/dev/null | wc -l)
    
    if [[ $chunk_count -eq 0 ]]; then
        print_color $YELLOW "Brak chunków do przetworzenia w $CHUNK_DIR"
        print_color $YELLOW "Najpierw uruchom dzielenie na chunki"
        wait_for_key
        return 1
    fi
    
    echo "Znaleziono: $chunk_count chunk(ów)"
    echo ""
    echo "Uwaga: Ta operacja wymaga skonfigurowanego API Qwen"
    echo ""
    
    if ! load_config; then
        print_color $YELLOW "⚠ Plik konfiguracyjny nie istnieje"
        read -p "Czy chcesz kontynuować bez konfiguracji API? (t/n): " confirm
        if [[ "$confirm" != "t" ]] && [[ "$confirm" != "T" ]]; then
            return 1
        fi
    fi
    
    echo "Rozpoczynanie przepisywania..."
    echo ""
    
    if [[ "$VERBOSE" == true ]]; then
        "$SCRIPT_DIR/rewrite_chunks.sh"
    else
        "$SCRIPT_DIR/rewrite_chunks.sh" 2>&1
    fi
    
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        print_color $GREEN "✓ Przepisywanie zakończone sukcesem"
    else
        print_color $RED "✗ Przepisywanie zakończone błędem (sprawdź konfigurację API)"
    fi
    
    wait_for_key
    return $result
}

run_full_pipeline() {
    print_menu_header "Pełny Pipeline"
    
    echo "Ten tryb uruchomi wszystkie etapy przetwarzania:"
    echo "  1. Konwersja plików do TXT"
    echo "  2. Dzielenie na chunki"
    echo "  3. Przepisywanie chunków"
    echo ""
    
    read -p "Czy na pewno chcesz uruchomić pełny pipeline? (t/n): " confirm
    if [[ "$confirm" != "t" ]] && [[ "$confirm" != "T" ]]; then
        return 0
    fi
    
    echo ""
    print_separator
    
    echo -e "${BOLD}Etap 1/3: Konwersja${NC}"
    run_conversion || return 1
    
    print_separator
    echo -e "${BOLD}Etap 2/3: Chunking${NC}"
    run_chunking || return 1
    
    print_separator
    echo -e "${BOLD}Etap 3/3: Przepisywanie${NC}"
    run_rewrite || return 1
    
    print_separator
    print_color $GREEN "✓ Pełny pipeline zakończony sukcesem!"
    
    wait_for_key
    return 0
}

# ============================================================================
# FUNKCJE TUI - MENU
# ============================================================================

show_status() {
    print_menu_header "Status systemu"
    
    echo -e "  ${BOLD}Katalogi:${NC}"
    for dir in "$INPUT_DIR" "$TMP_DIR" "$CHUNK_DIR" "$OUTPUT_DIR" "$LOGS_DIR"; do
        if [[ -d "$dir" ]]; then
            local count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l)
            echo -e "    ${GREEN}✓${NC} $dir ${DIM}($count plików)${NC}"
        else
            echo -e "    ${RED}✗${NC} $dir ${DIM}(nie istnieje)${NC}"
        fi
    done
    
    echo ""
    echo -e "  ${BOLD}Zależności:${NC}"
    command -v curl >/dev/null 2>&1 && echo -e "    ${GREEN}✓${NC} curl" || echo -e "    ${RED}✗${NC} curl"
    command -v jq >/dev/null 2>&1 && echo -e "    ${GREEN}✓${NC} jq" || echo -e "    ${RED}✗${NC} jq"
    command -v pandoc >/dev/null 2>&1 && echo -e "    ${GREEN}✓${NC} pandoc" || echo -e "    ${YELLOW}⚠${NC} pandoc (opcjonalny)"
    command -v pdftotext >/dev/null 2>&1 && echo -e "    ${GREEN}✓${NC} pdftotext" || echo -e "    ${YELLOW}⚠${NC} pdftotext (opcjonalny)"
    
    echo ""
    echo -e "  ${BOLD}Konfiguracja:${NC}"
    if [[ -f "$CONFIG_FILE" ]]; then
        echo -e "    ${GREEN}✓${NC} Plik konfiguracyjny istnieje"
    else
        echo -e "    ${YELLOW}⚠${NC} Plik konfiguracyjny nie istnieje"
    fi
    
    echo ""
    wait_for_key
}

show_logs() {
    print_menu_header "Logi systemu"
    
    if [[ ! -d "$LOGS_DIR" ]] || [[ -z "$(ls -A "$LOGS_DIR" 2>/dev/null)" ]]; then
        print_color $YELLOW "Brak plików logów w $LOGS_DIR"
        wait_for_key
        return 0
    fi
    
    local log_files=()
    while IFS= read -r -d '' file; do
        log_files+=("$file")
    done < <(find "$LOGS_DIR" -maxdepth 1 -type f -name "*.log" -print0 2>/dev/null)
    
    if [[ ${#log_files[@]} -eq 0 ]]; then
        print_color $YELLOW "Brak plików logów"
        wait_for_key
        return 0
    fi
    
    echo "Dostępne pliki logów:"
    echo ""
    
    for i in "${!log_files[@]}"; do
        local filename=$(basename "${log_files[$i]}")
        local lines=$(wc -l < "${log_files[$i]}")
        echo -e "  ${GREEN}$((i+1))${NC}) $filename ${DIM}($lines linii)${NC}"
    done
    
    echo -e "  ${GREEN}0${NC}) Powrót"
    echo ""
    
    while true; do
        read -p "  Wybierz numer pliku do podglądu (0-${#log_files[@]}): " choice
        
        if [[ "$choice" == "0" ]]; then
            return 0
        elif [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le "${#log_files[@]}" ]]; then
            local selected_log="${log_files[$((choice-1))]}"
            clear
            print_menu_header "Podgląd: $(basename "$selected_log")"
            echo -e "${DIM}(q - wyjście, Enter - przewiń)${NC}"
            echo ""
            
            # Podgląd ostatnich 50 linii
            tail -50 "$selected_log" | less -R
            
            return 0
        else
            print_color $RED "  Nieprawidłowy wybór"
        fi
    done
}

show_help() {
    print_menu_header "Pomoc"
    
    cat << EOF
  ${BOLD}BOOK REWRITING PIPELINE${NC}
  
  System do przepisywania książek wykorzystujący modele AI:
  • qwen-agent - Koordynator przepływu pracy
  • qwen-coder - Analiza struktury i kodu
  • qwen3.6-35B-A3B - Przetwarzanie treści
  
  ${BOLD}Tryby pracy:${NC}
  • cli   - Tryb tekstowy (domyślny)
  • tui   - Interfejs tekstowy (menu)
  • gui   - Interfejs graficzny (jeśli dostępny)
  • webui - Serwer webowy
  • daemon - Usługa w tle
  
  ${BOLD}Obsługiwane formaty:${NC}
  .doc, .docx, .odt, .pdf, .xls, .xlsx, .txt, .md
  
  ${BOLD}Struktura katalogów:${NC}
  /input  - Pliki wejściowe
  /tmp    - Pliki tymczasowe (TXT)
  /chunk  - Chunki z metadanymi
  /output - Wyniki końcowe
  /logs   - Logi procesu
  
EOF
    
    wait_for_key
}

main_menu() {
    while true; do
        clear
        print_header
        
        echo -e "${BOLD}MENU GŁÓWNE${NC}"
        echo ""
        print_separator
        
        print_option "1" "Status systemu"
        print_option "2" "Lista plików wejściowych"
        print_option "3" "Konwersja plików (do TXT)"
        print_option "4" "Dzielenie na chunki"
        print_option "5" "Przepisywanie chunków"
        print_option "6" "Uruchom pełny pipeline"
        print_separator
        print_option "L" "Przeglądaj logi"
        print_option "H" "Pomoc"
        print_option "Q" "Wyjście"
        print_separator
        
        echo ""
        read -p "  Wybierz opcję: " choice
        
        case $choice in
            1) show_status ;;
            2) list_input_files; wait_for_key ;;
            3) run_conversion ;;
            4) run_chunking ;;
            5) run_rewrite ;;
            6) run_full_pipeline ;;
            l|L) show_logs ;;
            h|H) show_help ;;
            q|Q) 
                echo ""
                print_color $CYAN "Dziękujemy za korzystanie z Book Rewriting Pipeline!"
                echo ""
                exit 0
                ;;
            *) print_color $RED "Nieznana opcja: $choice" ;;
        esac
    done
}

# ============================================================================
# TRYBY URUCHOMIENIA
# ============================================================================

run_cli_mode() {
    # Tryb CLI - argumenty wiersza poleceń
    print_header
    
    if [[ $# -eq 0 ]]; then
        echo "Użycie: $0 [opcje] [plik_wejściowy]"
        echo ""
        echo "Opcje:"
        echo "  -v, --verbose     Tryb szczegółowy"
        echo "  -d, --debug       Tryb debugowania"
        echo "  -h, --help        Wyświetl pomoc"
        echo "  -c, --convert     Tylko konwersja"
        echo "  -k, --chunk       Tylko chunking"
        echo "  -r, --rewrite     Tylko przepisywanie"
        echo "  -a, --all         Pełny pipeline"
        echo ""
        return 0
    fi
    
    local mode=""
    local target_file=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose) VERBOSE=true; shift ;;
            -d|--debug) DEBUG=true; VERBOSE=true; shift ;;
            -c|--convert) mode="convert"; shift ;;
            -k|--chunk) mode="chunk"; shift ;;
            -r|--rewrite) mode="rewrite"; shift ;;
            -a|--all) mode="all"; shift ;;
            -h|--help) 
                echo "Book Rewriting Pipeline - CLI Mode"
                echo ""
                echo "Użycie: $0 [opcje] [plik]"
                return 0
                ;;
            *)
                if [[ -f "$1" ]]; then
                    target_file="$1"
                else
                    print_color $RED "Nieznany argument: $1"
                    return 1
                fi
                shift
                ;;
        esac
    done
    
    init_directories
    
    case $mode in
        convert) run_conversion ;;
        chunk) run_chunking ;;
        rewrite) run_rewrite ;;
        all) run_full_pipeline ;;
        *) 
            if [[ -n "$target_file" ]]; then
                print_color $YELLOW "Podano plik, ale nie określono trybu. Używam TUI."
                main_menu
            else
                main_menu
            fi
            ;;
    esac
}

run_tui_mode() {
    # Tryb TUI - interfejs menu
    init_directories
    check_dependencies
    main_menu
}

run_daemon_mode() {
    local action="${1:-status}"
    local pid_file="$SCRIPT_DIR/pipeline.pid"
    
    case $action in
        start)
            if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
                print_color $YELLOW "Daemon już działa (PID: $(cat "$pid_file"))"
            else
                print_color $GREEN "Uruchamianie daemona..."
                nohup "$0" daemon run > "$LOGS_DIR/daemon.log" 2>&1 &
                echo $! > "$pid_file"
                print_color $GREEN "✓ Daemon uruchomiony (PID: $!)"
            fi
            ;;
        stop)
            if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
                kill "$(cat "$pid_file")"
                rm -f "$pid_file"
                print_color $GREEN "✓ Daemon zatrzymany"
            else
                print_color $YELLOW "Daemon nie działa"
            fi
            ;;
        status)
            if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
                print_color $GREEN "✓ Daemon działa (PID: $(cat "$pid_file"))"
            else
                print_color $YELLOW "✗ Daemon nie działa"
            fi
            ;;
        run)
            # Wewnętrzny tryb uruchomienia daemona
            log "INFO" "Daemon started"
            while true; do
                # Sprawdź nowe pliki w input co 60 sekund
                if [[ -d "$INPUT_DIR" ]]; then
                    local new_files=$(find "$INPUT_DIR" -type f -newer "$TEMP_DIR/.last_check" 2>/dev/null)
                    if [[ -n "$new_files" ]]; then
                        log "INFO" "Wykryto nowe pliki, uruchamianie pipeline..."
                        touch "$TEMP_DIR/.last_check"
                        # Tutaj można dodać automatyczne przetwarzanie
                    fi
                fi
                sleep 60
            done
            ;;
        restart)
            $0 daemon stop
            sleep 2
            $0 daemon start
            ;;
        *)
            print_color $RED "Nieznana akcja: $action"
            echo "Użycie: $0 daemon {start|stop|status|restart}"
            return 1
            ;;
    esac
}

run_webui_mode() {
    local port="${1:-8080}"
    
    print_color $CYAN "Uruchamianie WebUI na porcie $port..."
    print_color $YELLOW "⚠ Uwaga: WebUI wymaga dodatkowej implementacji"
    print_color $YELLOW "  Możesz użyć prostego serwera HTTP:"
    echo ""
    echo "  python3 -m http.server $port --directory $SCRIPT_DIR"
    echo ""
    print_color $YELLOW "  Lub zaimplementować własny serwer w bashu/node.js/python"
    
    # Prosta symulacja
    echo ""
    echo "Symulacja WebUI:"
    echo "  → http://localhost:$port"
    echo ""
    echo "Naciśnij Ctrl+C aby zatrzymać"
    
    # Gdyby był prawdziwy serwer:
    # cd "$SCRIPT_DIR" && python3 -m http.server "$port"
}

run_gui_mode() {
    print_color $CYAN "Uruchamianie GUI..."
    print_color $YELLOW "⚠ Uwaga: GUI wymaga dodatkowej implementacji"
    print_color $YELLOW "  Dostępne opcje:"
    echo ""
    echo "  • Tkinter (Python)"
    echo "  • Zenity (bash + GTK)"
    echo "  • Electron (JavaScript)"
    echo ""
    
    # Przykład z zenity (jeśli dostępne)
    if command -v zenity >/dev/null 2>&1; then
        zenity --info --text="Book Rewriting Pipeline GUI\n\nTo jest placeholder dla interfejsu graficznego." --width=400
    else
        print_color $YELLOW "Zainstaluj zenity dla podstawowego GUI: apt-get install zenity"
    fi
}

# ============================================================================
# GŁÓWNY PUNKT WEJŚCIA
# ============================================================================

main() {
    local mode="${1:-tui}"
    shift 2>/dev/null || true
    
    case $mode in
        cli)
            run_cli_mode "$@"
            ;;
        tui)
            run_tui_mode
            ;;
        gui)
            run_gui_mode
            ;;
        webui)
            run_webui_mode "$@"
            ;;
        daemon)
            run_daemon_mode "$@"
            ;;
        help|--help|-h)
            print_header
            echo "Użycie: $0 [tryb] [opcje]"
            echo ""
            echo "Dostępne tryby:"
            echo "  cli     - Tryb tekstowy z argumentami"
            echo "  tui     - Interfejs menu (domyślny)"
            echo "  gui     - Interfejs graficzny"
            echo "  webui   - Serwer webowy"
            echo "  daemon  - Usługa w tle"
            echo ""
            echo "Przykłady:"
            echo "  $0 tui"
            echo "  $0 cli --all input/book.pdf"
            echo "  $0 daemon start"
            echo "  $0 webui --port 8080"
            ;;
        *)
            print_color $RED "Nieznany tryb: $mode"
            echo "Użyj '$0 help' aby wyświetlić pomoc."
            exit 1
            ;;
    esac
}

# Uruchomienie
main "$@"
