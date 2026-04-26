#!/bin/bash
#
# Skrypt do przepisywania chunków z wykorzystaniem modeli Qwen
# 
# Architektura:
#   1. qwen-coder - analiza struktury, formatowanie, generowanie metadanych
#   2. qwen3.6-35B-A3B - głęboka analiza treści, przepisanie tekstu
#
# Użycie: ./rewrite_chunks.sh [-o output_dir] [chunk_dir]
#

set -e

# Ścieżki do katalogów (względne od lokalizacji skryptu)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHUNK_DIR="${1:-$SCRIPT_DIR/chunk}"
OUTPUT_DIR="$SCRIPT_DIR/output"
LOG_DIR="$SCRIPT_DIR/logs"

# Plik konfiguracyjny
CONFIG_FILE="$SCRIPT_DIR/config.sh"

# Ładowanie konfiguracji jeśli istnieje
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    # Domyślne wartości
    QWEN_API_KEY="${QWEN_API_KEY:-}"
    QWEN_CODER_URL="${QWEN_CODER_URL:-http://localhost:8000/v1/chat/completions}"
    QWEN_LARGE_MODEL_URL="${QWEN_LARGE_MODEL_URL:-http://localhost:8000/v1/chat/completions}"
    MAX_TOKENS="${MAX_TOKENS:-4096}"
    TEMPERATURE="${TEMPERATURE:-0.7}"
fi

# Funkcja logująca
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message"
    
    # Zapisz do logu jeśli katalog istnieje
    if [[ -d "$LOG_DIR" ]]; then
        echo "[$timestamp] [$level] $message" >> "$LOG_DIR/rewrite.log"
    fi
}

# Funkcja wysyłająca żądanie do API Qwen
call_qwen_api() {
    local model_url="$1"
    local model_name="$2"
    local prompt="$3"
    local system_message="$4"
    
    local response
    response=$(curl -s -X POST "$model_url" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $QWEN_API_KEY" \
        -d "{
            \"model\": \"$model_name\",
            \"messages\": [
                {\"role\": \"system\", \"content\": \"$system_message\"},
                {\"role\": \"user\", \"content\": \"$prompt\"}
            ],
            \"max_tokens\": $MAX_TOKENS,
            \"temperature\": $TEMPERATURE
        }")
    
    # Parsowanie odpowiedzi przy użyciu jq
    echo "$response" | jq -r '.choices[0].message.content // empty'
}

# Funkcja analizująca chunk za pomocą qwen-coder
analyze_with_coder() {
    local chunk_file="$1"
    local content="$2"
    
    log "INFO" "Analiza chunka $(basename "$chunk_file") za pomocą qwen-coder..."
    
    local system_msg="Jesteś asystentem AI specjalizującym się w analizie struktury tekstu i generowaniu metadanych. Twoim zadaniem jest przeanalizowanie dostarczonego tekstu pod kątem struktury, formatowania i identyfikacji kluczowych elementów."
    
    local prompt="Przeanalizuj poniższy tekst i zwróć:\n1. Strukturę tekstu (rozdziały, podrozdziały)\n2. Główne wątki/tematy\n3. Sugerowane formatowanie\n4. Kluczowe metadane\n\nTekst do analizy:\n$content"
    
    call_qwen_api "$QWEN_CODER_URL" "qwen-coder" "$prompt" "$system_msg"
}

# Funkcja przepisująca chunk za pomocą qwen3.6
rewrite_with_large_model() {
    local chunk_file="$1"
    local content="$2"
    local analysis="$3"
    
    log "INFO" "Przepisywanie chunka $(basename "$chunk_file") za pomocą qwen3.6-35B-A3B..."
    
    local system_msg="Jesteś zaawansowanym modelem językowym specjalizującym się w przepisywaniu i redagowaniu tekstów. Twoim zadaniem jest przepisanie dostarczonego tekstu z zachowaniem oryginalnego znaczenia, stylu i tonu, jednocześnie poprawiając czytelność i spójność."
    
    local prompt="Na podstawie poniższej analizy struktury przepisz tekst zachowując:\n- Oryginalne znaczenie i przesłanie\n- Styl i ton wypowiedzi\n- Poprawioną czytelność i flow\n- Spójność z kontekstem\n\nAnaliza struktury:\n$analysis\n\nTekst do przepisania:\n$content"
    
    call_qwen_api "$QWEN_LARGE_MODEL_URL" "qwen3.6-35B-A3B" "$prompt" "$system_msg"
}

# Główna funkcja przetwarzająca pojedynczy chunk
process_chunk() {
    local chunk_file="$1"
    local filename=$(basename "$chunk_file")
    local output_file="$OUTPUT_DIR/${filename%.json}_rewritten.json"
    
    log "INFO" "Przetwarzanie pliku: $filename"
    
    # Sprawdzenie czy plik istnieje
    if [[ ! -f "$chunk_file" ]]; then
        log "ERROR" "Plik nie istnieje: $chunk_file"
        return 1
    fi
    
    # Wczytanie zawartości chunka
    local content
    content=$(cat "$chunk_file")
    
    # Ekstrakcja samego tekstu z JSON (pole 'content')
    local text_content
    text_content=$(echo "$content" | jq -r '.content // empty')
    
    if [[ -z "$text_content" ]]; then
        # Jeśli to zwykły plik tekstowy (nie JSON), użyj całej zawartości
        text_content="$content"
    fi
    
    # Etap 1: Analiza za pomocą qwen-coder
    local analysis
    analysis=$(analyze_with_coder "$chunk_file" "$text_content")
    
    if [[ -z "$analysis" ]]; then
        log "WARN" "Brak odpowiedzi od qwen-coder dla $filename, kontynuuję bez analizy..."
        analysis="Brak szczegółowej analizy - kontynuacja z oryginalnym tekstem."
    fi
    
    log "DEBUG" "Analiza zakończona dla $filename"
    
    # Etap 2: Przepisanie za pomocą qwen3.6
    local rewritten_content
    rewritten_content=$(rewrite_with_large_model "$chunk_file" "$text_content" "$analysis")
    
    if [[ -z "$rewritten_content" ]]; then
        log "ERROR" "Brak odpowiedzi od qwen3.6 dla $filename"
        return 1
    fi
    
    log "DEBUG" "Przepisywanie zakończone dla $filename"
    
    # Przygotowanie outputu z metadanymi
    local output_json
    if echo "$content" | jq -e . >/dev/null 2>&1; then
        # Jeśli wejście było JSON, zachowaj strukturę i zaktualizuj content
        output_json=$(echo "$content" | jq --arg new_content "$rewritten_content" '.content = $new_content')
    else
        # Jeśli wejście było zwykłym tekstem, utwórz prosty JSON
        output_json=$(jq -n --arg content "$rewritten_content" '{content: $content}')
    fi
    
    # Zapis wyniku
    echo "$output_json" > "$output_file"
    
    log "INFO" "Zapisano przetworzony plik: $output_file"
    
    return 0
}

# Funkcja główna
main() {
    log "INFO" "=========================================="
    log "INFO" "Rozpoczynanie procesu przepisywania chunków"
    log "INFO" "=========================================="
    
    # Sprawdzenie czy katalog chunk istnieje
    if [[ ! -d "$CHUNK_DIR" ]]; then
        log "ERROR" "Katalog chunk nie istnieje: $CHUNK_DIR"
        exit 1
    fi
    
    # Utworzenie katalogu output jeśli nie istnieje
    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$LOG_DIR"
    
    # Liczniki
    local total=0
    local success=0
    local failed=0
    
    # Przetwarzanie wszystkich plików z katalogu chunk
    for chunk_file in "$CHUNK_DIR"/*; do
        # Sprawdzenie czy są jakieś pliki
        if [[ ! -e "$chunk_file" ]]; then
            log "WARN" "Brak plików w katalogu $CHUNK_DIR"
            break
        fi
        
        # Pomijanie katalogów
        if [[ -d "$chunk_file" ]]; then
            continue
        fi
        
        ((total++)) || true
        
        if process_chunk "$chunk_file"; then
            ((success++)) || true
        else
            ((failed++)) || true
            log "ERROR" "Nie udało się przetworzyć: $(basename "$chunk_file")"
        fi
    done
    
    log "INFO" "=========================================="
    log "INFO" "Podsumowanie:"
    log "INFO" "  - Łącznie plików: $total"
    log "INFO" "  - Sukcesów: $success"
    log "INFO" "  - Niepowodzeń: $failed"
    log "INFO" "=========================================="
    
    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
    
    log "INFO" "Przetwarzanie zakończone. Wyniki zapisane w: $OUTPUT_DIR"
    exit 0
}

# Uruchomienie skryptu
main "$@"
