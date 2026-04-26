#!/bin/bash
#
# Skrypt instalacyjny i konfiguracyjny dla Book Rewriting Pipeline
# Instaluje zależności, tworzy katalogi i konfiguruje środowisko
#
# Użycie: ./install.sh [opcje]
#

set -e

# Kolory dla outputu
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Ścieżki
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"
CONFIG_EXAMPLE="$SCRIPT_DIR/config.sh.example"

# Zmienne konfiguracyjne
INSTALL_MODELS=false
CONFIGURE_API=false
SKIP_DEPENDENCIES=false
VERBOSE=false

# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     BOOK REWRITING PIPELINE - Instalator i Konfigurator      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}➜${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

log() {
    if [[ "$VERBOSE" == true ]]; then
        echo -e "  ${DIM}[$(date '+%H:%M:%S')]${NC} $1"
    fi
}

show_help() {
    cat << EOF
Skrypt instalacyjny i konfiguracyjny Book Rewriting Pipeline

Użycie: $(basename "$0") [OPCJE]

OPCJE:
    -m, --models          Dodatkowa instalacja modeli AI (Ollama/vLLM)
    -c, --configure       Interaktywna konfiguracja API
    -s, --skip-deps       Pominięcie instalacji zależności systemowych
    -v, --verbose         Tryb szczegółowy
    -h, --help            Wyświetl tę pomoc i zakończ

PRZYKŁADY:
    $(basename "$0")                     # Standardowa instalacja
    $(basename "$0") -m                  # Instalacja z modelami AI
    $(basename "$0") -c                  # Tylko konfiguracja API
    $(basename "$0") -m -c -v            # Pełna instalacja z konfiguracją

EOF
    exit 0
}

# ============================================================================
# PARSOWANIE ARGUMENTÓW
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--models)
            INSTALL_MODELS=true
            shift
            ;;
        -c|--configure)
            CONFIGURE_API=true
            shift
            ;;
        -s|--skip-deps)
            SKIP_DEPENDENCIES=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
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
# FUNKCJE INSTALACYJNE
# ============================================================================

check_root() {
    print_step "Sprawdzanie uprawnień"
    if [[ $EUID -eq 0 ]]; then
        print_warning "Uruchomiono jako root. Zalecane jest uruchomienie jako zwykły użytkownik."
    else
        print_success "Uprawnienia użytkownika OK"
    fi
}

check_os() {
    print_step "Wykrywanie systemu operacyjnego"
    
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID=$ID
        OS_VERSION=$VERSION_ID
        print_success "Wykryto system: $NAME $VERSION"
    elif [[ -f /etc/debian_version ]]; then
        OS_ID="debian"
        print_success "Wykryto system: Debian"
    elif [[ -f /etc/redhat-release ]]; then
        OS_ID="rhel"
        print_success "Wykryto system: Red Hat Enterprise Linux"
    else
        OS_ID="unknown"
        print_warning "Nieznany system operacyjny, próba kontynuacji..."
    fi
}

install_dependencies_debian() {
    print_step "Instalowanie zależności (Debian/Ubuntu)"
    
    local packages=(
        "curl"
        "jq"
        "git"
        "wget"
        "unzip"
        "python3"
        "python3-pip"
        "python3-venv"
    )
    
    # Opcjonalne pakiety do konwersji dokumentów
    local optional_packages=(
        "pandoc"
        "poppler-utils"
        "libreoffice-common"
    )
    
    log "Aktualizacja listy pakietów..."
    sudo apt-get update -qq
    
    log "Instalowanie podstawowych zależności..."
    for pkg in "${packages[@]}"; do
        if ! dpkg -l | grep -q "^ii  $pkg "; then
            log "  Instalowanie: $pkg"
            sudo apt-get install -y -qq "$pkg" || print_warning "Nie udało się zainstalować $pkg"
        else
            log "  $pkg już zainstalowany"
        fi
    done
    
    log "Instalowanie opcjonalnych narzędzi do konwersji..."
    for pkg in "${optional_packages[@]}"; do
        if ! dpkg -l | grep -q "^ii  $pkg "; then
            log "  Instalowanie: $pkg"
            sudo apt-get install -y -qq "$pkg" || print_warning "Nie udało się zainstalować $pkg (opcjonalny)"
        else
            log "  $pkg już zainstalowany"
        fi
    done
    
    print_success "Zależności zainstalowane"
}

install_dependencies_rhel() {
    print_step "Instalowanie zależności (RHEL/CentOS/Fedora)"
    
    local packages=(
        "curl"
        "jq"
        "git"
        "wget"
        "unzip"
        "python3"
        "python3-pip"
    )
    
    log "Instalowanie zależności..."
    for pkg in "${packages[@]}"; do
        if ! rpm -q "$pkg" &>/dev/null; then
            log "  Instalowanie: $pkg"
            sudo dnf install -y -q "$pkg" || sudo yum install -y -q "$pkg" || print_warning "Nie udało się zainstalować $pkg"
        else
            log "  $pkg już zainstalowany"
        fi
    done
    
    print_success "Zależności zainstalowane"
}

install_dependencies() {
    if [[ "$SKIP_DEPENDENCIES" == true ]]; then
        print_warning "Pominięto instalację zależności (--skip-deps)"
        return 0
    fi
    
    case $OS_ID in
        ubuntu|debian|linuxmint)
            install_dependencies_debian
            ;;
        rhel|centos|fedora|rocky|almalinux)
            install_dependencies_rhel
            ;;
        arch|manjaro)
            print_warning "System Arch/Manjaro wykryty. Zainstaluj ręcznie: pacman -S curl jq git wget unzip python python-pip"
            ;;
        *)
            print_warning "Nieznany system. Spróbuj zainstalować zależności ręcznie:"
            echo "  - curl"
            echo "  - jq"
            echo "  - git"
            echo "  - python3"
            ;;
    esac
}

setup_python_environment() {
    print_step "Konfiguracja środowiska Python"
    
    # Sprawdzenie czy Python3 jest dostępny
    if ! command -v python3 &>/dev/null; then
        print_error "Python3 nie jest zainstalowany"
        return 1
    fi
    
    local python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    log "Wersja Python: $python_version"
    
    # Tworzenie wirtualnego środowiska jeśli nie istnieje
    if [[ ! -d "$SCRIPT_DIR/venv" ]]; then
        log "Tworzenie wirtualnego środowiska..."
        python3 -m venv "$SCRIPT_DIR/venv"
        print_success "Utworzono wirtualne środowisko"
    else
        log "Wirtualne środowisko już istnieje"
    fi
    
    # Aktywacja wirtualnego środowiska
    source "$SCRIPT_DIR/venv/bin/activate"
    
    # Instalacja zależności Python
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        log "Instalowanie zależności Python..."
        pip install --upgrade pip -q
        pip install -r "$SCRIPT_DIR/requirements.txt" -q
        print_success "Zależności Python zainstalowane"
    else
        log "Brak pliku requirements.txt, instalowanie podstawowych pakietów..."
        pip install --upgrade pip -q
        pip install requests flask gradio -q
        print_success "Podstawowe pakiety Python zainstalowane"
    fi
    
    deactivate
    print_success "Środowisko Python skonfigurowane"
}

create_directories() {
    print_step "Tworzenie struktury katalogów"
    
    local directories=(
        "input"
        "tmp"
        "chunk"
        "output"
        "logs"
        "temp"
        "/finish"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log "  Utworzono: $dir"
        else
            log "  Istnieje: $dir"
        fi
    done
    
    # Ustawienie odpowiednich uprawnień
    chmod 755 "${directories[@]}" 2>/dev/null || true
    
    print_success "Struktura katalogów utworzona"
}

setup_config_file() {
    print_step "Konfiguracja pliku config.sh"
    
    # Jeśli config.sh już istnieje, zrób kopię zapasową
    if [[ -f "$CONFIG_FILE" ]]; then
        local backup_file="${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$CONFIG_FILE" "$backup_file"
        log "  Utworzono kopię zapasową: $backup_file"
    fi
    
    # Jeśli config.sh.example nie istnieje, utwórz go
    if [[ ! -f "$CONFIG_EXAMPLE" ]]; then
        create_config_example
    fi
    
    # Kopiuj przykład do config.sh jeśli config.sh nie istnieje
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        log "  Utworzono plik konfiguracyjny na podstawie szablonu"
    fi
    
    # Interaktywna konfiguracja jeśli requested
    if [[ "$CONFIGURE_API" == true ]]; then
        interactive_configure
    fi
    
    # Ustawienie restrykcyjnych uprawnień dla pliku z kluczami API
    chmod 600 "$CONFIG_FILE"
    
    print_success "Plik konfiguracyjny gotowy"
}

create_config_example() {
    log "  Tworzenie szablonu konfiguracji..."
    
    cat > "$CONFIG_EXAMPLE" << 'EOF'
#!/bin/bash
#
# Plik konfiguracyjny Book Rewriting Pipeline
# Skopiuj ten plik jako config.sh i wypełnij swoimi danymi
#
# UWAGA: Nigdy nie commituj pliku config.sh z prawdziwymi kluczami API!
#

# ============================================================================
# KONFIGURACJA API QWEN
# ============================================================================

# Klucz API do usług Alibaba Cloud / Qwen
# Uzyskaj na: https://dashscope.console.aliyun.com/
QWEN_API_KEY="your-api-key-here"

# Endpointy API (dostosuj do swojej infrastruktury)
# Domyślnie: lokalny serwer lub cloud API

# qwen-agent - koordynator przepływu pracy
QWEN_AGENT_URL="http://localhost:8000/v1/chat/completions"
# lub cloud: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# qwen-coder - analiza struktury i kodu
QWEN_CODER_URL="http://localhost:8000/v1/chat/completions"
# lub cloud: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# qwen3.6-35B-A3B - duży model do przetwarzania treści
QWEN_LARGE_MODEL_URL="http://localhost:8000/v1/chat/completions"
# lub cloud: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# ============================================================================
# PARAMETRY MODELI
# ============================================================================

# Maksymalna liczba tokenów w odpowiedzi
MAX_TOKENS=4096

# Temperatura (0.0 - 1.0): wyższa = bardziej kreatywny, niższa = bardziej deterministyczny
TEMPERATURE=0.7

# Top-p (nucleus sampling)
TOP_P=0.9

# Limit powtórzeń przy błędach API
MAX_RETRIES=3

# Timeout żądań HTTP w sekundach
HTTP_TIMEOUT=120

# ============================================================================
# ŚCIEŻKI I KATALOGI
# ============================================================================

# Katalogi robocze (relative do script_dir)
INPUT_DIR="./input"
TMP_DIR="./tmp"
CHUNK_DIR="./chunk"
OUTPUT_DIR="./output"
FINISH_DIR="/finish"
LOGS_DIR="./logs"
TEMP_DIR="./temp"

# ============================================================================
# OPCJE PRZETWARZANIA
# ============================================================================

# Domyślny rozmiar chunka w tokenach
DEFAULT_CHUNK_SIZE=4096

# Czy używać cache dla przetworzonych chunków
USE_CACHE=true
CACHE_DIR="./cache"

# Czy kontynuować po błędzie pojedynczego chunka
CONTINUE_ON_ERROR=true

# Liczba równoległych żądań API (jeśli wspierane)
PARALLEL_REQUESTS=1

# ============================================================================
# LOGOWANIE
# ============================================================================

# Poziom logowania: DEBUG, INFO, WARN, ERROR
LOG_LEVEL="INFO"

# Czy zapisywać logi do plików
LOG_TO_FILE=true

# Czy wyświetlać logi w konsoli
LOG_TO_CONSOLE=true

# ============================================================================
# INNE USTAWIENIA
# ============================================================================

# Wersja pipeline
PIPELINE_VERSION="1.0.0"

# Czy sprawdzać aktualizacje
CHECK_UPDATES=true

# Proxy settings (jeśli wymagane)
# HTTP_PROXY="http://proxy.example.com:8080"
# HTTPS_PROXY="http://proxy.example.com:8080"
# NO_PROXY="localhost,127.0.0.1"

EOF
    
    print_success "Utworzono szablon konfiguracji: $CONFIG_EXAMPLE"
}

interactive_configure() {
    echo ""
    echo -e "${BOLD}=== Interaktywna konfiguracja API ===${NC}"
    echo ""
    
    read -p "Podaj swój klucz API Qwen (ENTER aby pominąć): " api_key
    if [[ -n "$api_key" ]]; then
        sed -i "s/QWEN_API_KEY=\"your-api-key-here\"/QWEN_API_KEY=\"$api_key\"/" "$CONFIG_FILE"
        print_success "Zapisano klucz API"
    fi
    
    echo ""
    echo "Wybierz typ konfiguracji endpointów:"
    echo "  1) Lokalny serwer (Ollama/vLLM) - domyślne"
    echo "  2) Alibaba Cloud DashScope"
    echo "  3) Własna konfiguracja (ręczna edycja)"
    echo ""
    
    read -p "Wybierz opcję (1-3): " endpoint_choice
    
    case $endpoint_choice in
        2)
            # Alibaba Cloud
            sed -i 's|QWEN_AGENT_URL="http://localhost:8000.*|QWEN_AGENT_URL="https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"|' "$CONFIG_FILE"
            sed -i 's|QWEN_CODER_URL="http://localhost:8000.*|QWEN_CODER_URL="https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"|' "$CONFIG_FILE"
            sed -i 's|QWEN_LARGE_MODEL_URL="http://localhost:8000.*|QWEN_LARGE_MODEL_URL="https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"|' "$CONFIG_FILE"
            print_success "Skonfigurowano endpointy Alibaba Cloud"
            ;;
        3)
            print_info "Możesz edytować plik config.sh ręcznie później"
            ;;
        *)
            print_success "Pozostawiono domyślne endpointy lokalne"
            ;;
    esac
    
    echo ""
    read -p "Czy chcesz dostosować parametry modeli? (t/n): " customize_params
    
    if [[ "$customize_params" == "t" ]] || [[ "$customize_params" == "T" ]]; then
        read -p "Maksymalna liczba tokenów (domyślnie 4096): " max_tokens
        if [[ -n "$max_tokens" ]]; then
            sed -i "s/MAX_TOKENS=.*/MAX_TOKENS=$max_tokens/" "$CONFIG_FILE"
        fi
        
        read -p "Temperatura (0.0-1.0, domyślnie 0.7): " temperature
        if [[ -n "$temperature" ]]; then
            sed -i "s/TEMPERATURE=.*/TEMPERATURE=$temperature/" "$CONFIG_FILE"
        fi
    fi
    
    echo ""
    print_success "Konfiguracja zakończona"
}

install_models_ollama() {
    print_step "Instalacja modeli AI przez Ollama"
    
    # Sprawdzenie czy Ollama jest zainstalowana
    if ! command -v ollama &>/dev/null; then
        print_warning "Ollama nie jest zainstalowana"
        echo "  Instalacja Ollama: curl -fsSL https://ollama.com/install.sh | sh"
        
        read -p "Czy zainstalować Ollama teraz? (t/n): " install_ollama
        
        if [[ "$install_ollama" == "t" ]] || [[ "$install_ollama" == "T" ]]; then
            curl -fsSL https://ollama.com/install.sh | sh
            print_success "Ollama zainstalowana"
        else
            print_warning "Pominięto instalację modeli"
            return 0
        fi
    fi
    
    # Uruchomienie serwera Ollama w tle jeśli nie działa
    if ! pgrep -x "ollama" > /dev/null; then
        log "Uruchamianie serwera Ollama..."
        ollama serve &
        sleep 5
    fi
    
    # Modele do zainstalowania
    local models=(
        "qwen:7b"
        "qwen:14b"
        "codellama:7b"
    )
    
    echo ""
    echo "Dostępne modele Qwen do instalacji:"
    echo "  1) qwen:7b - lekki model do prostych zadań"
    echo "  2) qwen:14b - średni model, dobry balans"
    echo "  3) qwen:32b - duży model, lepsza jakość"
    echo "  4) Wszystkie powyższe"
    echo "  5) Pomiń instalację modeli"
    echo ""
    
    read -p "Wybierz modele do instalacji (1-5): " model_choice
    
    case $model_choice in
        1)
            models=("qwen:7b")
            ;;
        2)
            models=("qwen:14b")
            ;;
        3)
            models=("qwen:32b")
            ;;
        4)
            models=("qwen:7b" "qwen:14b" "qwen:32b")
            ;;
        *)
            print_warning "Pominięto instalację modeli"
            return 0
            ;;
    esac
    
    for model in "${models[@]}"; do
        echo ""
        log "Pobieranie modelu: $model"
        ollama pull "$model"
        print_success "Model $model zainstalowany"
    done
    
    # Aktualizacja konfiguracji dla Ollama
    if [[ -f "$CONFIG_FILE" ]]; then
        sed -i 's|QWEN_AGENT_URL=".*"|QWEN_AGENT_URL="http://localhost:11434/api/chat"|' "$CONFIG_FILE"
        sed -i 's|QWEN_CODER_URL=".*"|QWEN_CODER_URL="http://localhost:11434/api/chat"|' "$CONFIG_FILE"
        sed -i 's|QWEN_LARGE_MODEL_URL=".*"|QWEN_LARGE_MODEL_URL="http://localhost:11434/api/chat"|' "$CONFIG_FILE"
        print_success "Zaktualizowano konfigurację dla Ollama"
    fi
}

install_models_vllm() {
    print_step "Konfiguracja vLLM dla modeli Qwen"
    
    # Sprawdzenie czy vLLM jest zainstalowane
    if ! command -v vllm &>/dev/null; then
        print_warning "vLLM nie jest zainstalowane"
        echo "  Instalacja: pip install vllm"
        
        read -p "Czy zainstalować vLLM teraz? (t/n): " install_vllm
        
        if [[ "$install_vllm" == "t" ]] || [[ "$install_vllm" == "T" ]]; then
            source "$SCRIPT_DIR/venv/bin/activate"
            pip install vllm
            deactivate
            print_success "vLLM zainstalowane"
        else
            print_warning "Pominięto instalację vLLM"
            return 0
        fi
    fi
    
    echo ""
    echo "vLLM wymaga podania ścieżki do modelu lub nazwy z HuggingFace"
    read -p "Podaj nazwę modelu (np. Qwen/Qwen-7B-Chat): " model_name
    
    if [[ -n "$model_name" ]]; then
        echo ""
        echo "Przykładowa komenda uruchomienia serwera vLLM:"
        echo -e "${CYAN}"
        echo "python -m vllm.entrypoints.api_server \\"
        echo "    --model $model_name \\"
        echo "    --host 0.0.0.0 \\"
        echo "    --port 8000"
        echo -e "${NC}"
        
        read -p "Czy utworzyć skrypt startowy dla vLLM? (t/n): " create_script
        
        if [[ "$create_script" == "t" ]] || [[ "$create_script" == "T" ]]; then
            cat > "$SCRIPT_DIR/start_vllm.sh" << EOF
#!/bin/bash
# Skrypt startowy dla vLLM

MODEL_NAME="${model_name:-Qwen/Qwen-7B-Chat}"
HOST="0.0.0.0"
PORT="8000"

echo "Uruchamianie vLLM z modelem: \$MODEL_NAME"

source "\$(dirname \"\$0\")/venv/bin/activate"

python -m vllm.entrypoints.api_server \\
    --model "\$MODEL_NAME" \\
    --host "\$HOST" \\
    --port "\$PORT"
EOF
            chmod +x "$SCRIPT_DIR/start_vllm.sh"
            print_success "Utworzono skrypt startowy: start_vllm.sh"
        fi
    fi
}

install_models() {
    if [[ "$INSTALL_MODELS" != true ]]; then
        return 0
    fi
    
    echo ""
    echo -e "${BOLD}=== Instalacja modeli AI ===${NC}"
    echo ""
    echo "Wybierz metodę instalacji modeli:"
    echo "  1) Ollama (najprostsza, polecana dla początkujących)"
    echo "  2) vLLM (zaawansowana, lepsza wydajność)"
    echo "  3) Pomiń instalację modeli"
    echo ""
    
    read -p "Wybierz opcję (1-3): " method_choice
    
    case $method_choice in
        1)
            install_models_ollama
            ;;
        2)
            install_models_vllm
            ;;
        *)
            print_warning "Pominięto instalację modeli"
            ;;
    esac
}

make_scripts_executable() {
    print_step "Ustawianie uprawnień wykonywalności dla skryptów"
    
    for script in "$SCRIPT_DIR"/*.sh; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            log "  Ustawiono +x: $(basename "$script")"
        fi
    done
    
    print_success "Skrypty są wykonywalne"
}

verify_installation() {
    print_step "Weryfikacja instalacji"
    
    local errors=0
    
    # Sprawdzenie zależności
    for cmd in curl jq; do
        if command -v "$cmd" &>/dev/null; then
            log "  ✓ $cmd"
        else
            log "  ✗ $cmd (brak)"
            ((errors++)) || true
        fi
    done
    
    # Sprawdzenie katalogów
    for dir in input tmp chunk output logs; do
        if [[ -d "$SCRIPT_DIR/$dir" ]]; then
            log "  ✓ katalog $dir"
        else
            log "  ✗ katalog $dir (brak)"
            ((errors++)) || true
        fi
    done
    
    # Sprawdzenie konfiguracji
    if [[ -f "$CONFIG_FILE" ]]; then
        log "  ✓ plik konfiguracyjny"
    else
        log "  ✗ plik konfiguracyjny (brak)"
        ((errors++)) || true
    fi
    
    # Sprawdzenie skryptów
    for script in pipeline.sh convert_to_txt.sh chunk_script.sh rewrite_chunks.sh; do
        if [[ -x "$SCRIPT_DIR/$script" ]]; then
            log "  ✓ skrypt $script"
        else
            log "  ✗ skrypt $script (brak lub niewykonywalny)"
            ((errors++)) || true
        fi
    done
    
    echo ""
    if [[ $errors -eq 0 ]]; then
        print_success "Instalacja zakończona pomyślnie!"
        return 0
    else
        print_warning "Instalacja zakończona z $errors błędem(ami)"
        return 1
    fi
}

show_next_steps() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}Następne kroki:${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "1. Edytuj plik konfiguracyjny:"
    echo -e "   ${YELLOW}nano config.sh${NC}"
    echo ""
    echo "2. Dodaj swoje klucze API i skonfiguruj endpointy"
    echo ""
    echo "3. Umieść pliki książek w katalogu:"
    echo -e "   ${YELLOW}./input/${NC}"
    echo ""
    echo "4. Uruchom pipeline:"
    echo -e "   ${YELLOW}./pipeline.sh${NC}"
    echo ""
    echo "5. Lub uruchom interfejs webowy:"
    echo -e "   ${YELLOW}./pipeline.sh webui${NC}"
    echo ""
    echo -e "Więcej informacji znajdziesz w pliku ${BOLD}README.md${NC}"
    echo ""
}

# ============================================================================
# GŁÓWNA FUNKCJA
# ============================================================================

main() {
    print_header
    
    echo ""
    print_step "Rozpoczynanie instalacji Book Rewriting Pipeline"
    echo ""
    
    check_root
    check_os
    
    if [[ "$SKIP_DEPENDENCIES" != true ]]; then
        install_dependencies
    fi
    
    setup_python_environment
    create_directories
    setup_config_file
    
    if [[ "$INSTALL_MODELS" == true ]]; then
        install_models
    fi
    
    make_scripts_executable
    verify_installation
    show_next_steps
    
    print_success "Instalacja zakończona!"
    echo ""
}

# Uruchomienie skryptu
main "$@"
