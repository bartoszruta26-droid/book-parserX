#!/bin/bash

# Skrypt do dzielenia plików tekstowych na chunki (domyślnie 4096 tokenów)
# i zapisywania ich w katalogu /chunk z metadanymi JSON

# Domyślne wartości
CHUNK_SIZE=${CHUNK_SIZE:-4096}
OUTPUT_DIR="/chunk"
INPUT_FILE=""

# Funkcja pomocnicza do wyświetlania użycia
usage() {
    echo "Użycie: $0 [-s rozmiar_chunka] [-o katalog_wyjściowy] <plik_wejściowy>"
    echo "  -s  Rozmiar chunka w tokenach (domyślnie: 4096)"
    echo "  -o  Katalog wyjściowy (domyślnie: /chunk)"
    echo "  -h  Wyświetl tę pomoc"
    exit 1
}

# Parsowanie argumentów
while getopts "s:o:h" opt; do
    case $opt in
        s) CHUNK_SIZE="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND-1))

# Sprawdzenie czy podano plik wejściowy
if [ $# -lt 1 ]; then
    echo "Błąd: Nie podano pliku wejściowego"
    usage
fi

INPUT_FILE="$1"

# Sprawdzenie czy plik istnieje
if [ ! -f "$INPUT_FILE" ]; then
    echo "Błąd: Plik '$INPUT_FILE' nie istnieje"
    exit 1
fi

# Tworzenie katalogu wyjściowego
mkdir -p "$OUTPUT_DIR"

# Pobieranie nazwy pliku bez rozszerzenia
BASENAME=$(basename "$INPUT_FILE")
FILENAME="${BASENAME%.*}"

# Funkcja do szacowania liczby tokenów (przybliżenie: 1 token ≈ 4 znaki)
estimate_tokens() {
    local text="$1"
    local char_count=${#text}
    echo $((char_count / 4))
}

# Czytanie pliku i dzielenie na chunki
echo "Dzielenie pliku '$INPUT_FILE' na chunki po ~$CHUNK_SIZE tokenów..."

chunk_number=0
current_chunk=""
current_tokens=0
declare -a chunk_files=()
declare -a chunk_sizes=()
declare -a chunk_start_lines=()

line_number=0
start_line=1

while IFS= read -r line || [ -n "$line" ]; do
    line_number=$((line_number + 1))
    
    # Szacowanie tokenów w bieżącej linii
    line_tokens=$(estimate_tokens "$line")
    
    # Sprawdzenie czy dodanie linii przekroczy limit
    if [ $((current_tokens + line_tokens)) -gt $CHUNK_SIZE ] && [ -n "$current_chunk" ]; then
        # Zapisywanie текущего chunka
        chunk_file="${OUTPUT_DIR}/${FILENAME}_chunk_${chunk_number}.txt"
        echo -n "$current_chunk" > "$chunk_file"
        
        chunk_files+=("$chunk_file")
        chunk_sizes+=("$current_tokens")
        chunk_start_lines+=("$start_line")
        
        echo "Zapisano chunk $chunk_number (${current_tokens} tokenów, linie $start_line-$((line_number-1)))"
        
        # Resetowanie dla nowego chunka
        current_chunk="$line"$'\n'
        current_tokens=$line_tokens
        start_line=$line_number
        chunk_number=$((chunk_number + 1))
    else
        # Dodawanie linii do текущего chunka
        current_chunk+="$line"$'\n'
        current_tokens=$((current_tokens + line_tokens))
    fi
done < "$INPUT_FILE"

# Zapisywanie ostatniego chunka jeśli coś pozostało
if [ -n "$current_chunk" ]; then
    chunk_file="${OUTPUT_DIR}/${FILENAME}_chunk_${chunk_number}.txt"
    echo -n "$current_chunk" > "$chunk_file"
    
    chunk_files+=("$chunk_file")
    chunk_sizes+=("$current_tokens")
    chunk_start_lines+=("$start_line")
    
    echo "Zapisano chunk $chunk_number (${current_tokens} tokenów, linie $start_line-$line_number)"
    chunk_number=$((chunk_number + 1))
fi

total_chunks=${#chunk_files[@]}
echo "Łącznie utworzono $total_chunks chunków"

# Tworzenie pliku metadanych JSON
metadata_file="${OUTPUT_DIR}/${FILENAME}_metadata.json"

echo "Tworzenie pliku metadanych: $metadata_file"

# Budowanie JSON z metadanymi
{
    echo "{"
    echo "  \"source_file\": \"$INPUT_FILE\","
    echo "  \"chunk_size_target\": $CHUNK_SIZE,"
    echo "  \"total_chunks\": $total_chunks,"
    echo "  \"created_at\": \"$(date -Iseconds)\","
    echo "  \"chunks\": ["
    
    for i in "${!chunk_files[@]}"; do
        chunk_file="${chunk_files[$i]}"
        chunk_size="${chunk_sizes[$i]}"
        chunk_start="${chunk_start_lines[$i]}"
        
        # Obliczanie linii końcowej
        if [ $((i + 1)) -lt $total_chunks ]; then
            chunk_end=$((chunk_start_lines[$i + 1] - 1))
        else
            chunk_end=$line_number
        fi
        
        # Poprzedni i następny chunk
        prev_chunk="null"
        next_chunk="null"
        
        if [ $i -gt 0 ]; then
            prev_chunk="\"${chunk_files[$((i-1))]}\""
        fi
        
        if [ $((i + 1)) -lt $total_chunks ]; then
            next_chunk="\"${chunk_files[$((i+1))]}\""
        fi
        
        echo "    {"
        echo "      \"chunk_id\": $i,"
        echo "      \"filename\": \"$(basename "$chunk_file")\","
        echo "      \"filepath\": \"$chunk_file\","
        echo "      \"token_count\": $chunk_size,"
        echo "      \"line_start\": $chunk_start,"
        echo "      \"line_end\": $chunk_end,"
        echo "      \"previous_chunk\": $prev_chunk,"
        echo "      \"next_chunk\": $next_chunk,"
        
        # Lista wszystkich chunków dla kontekstu
        echo "      \"all_chunks\": ["
        for j in "${!chunk_files[@]}"; do
            if [ $j -eq 0 ]; then
                echo -n "        {\"id\": $j, \"file\": \"$(basename "${chunk_files[$j]}")\", \"tokens\": ${chunk_sizes[$j]}}"
            else
                echo -n ",
        {\"id\": $j, \"file\": \"$(basename "${chunk_files[$j]}")\", \"tokens\": ${chunk_sizes[$j]}}"
            fi
        done
        echo ""
        echo "      ]"
        
        if [ $i -lt $((total_chunks - 1)) ]; then
            echo "    },"
        else
            echo "    }"
        fi
    done
    
    echo "  ]"
    echo "}"
} > "$metadata_file"

echo "Gotowe! Chunki zapisano w katalogu: $OUTPUT_DIR"
echo "Metadane dostępne w: $metadata_file"
