#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Book Rewriting Pipeline - WebUI v2.0
Rozszerzony interfejs webowy z integracją Qwen-Agent i obsługą klastra Raspberry Pi

Funkcje:
    - Zarządzanie pipeline'em przepisywania książek z AI
    - Obsługa klastra 6节点 (3x RPi4 + 3x RPi1) w trybie szeregowym/równoległym
    - Integracja z Qwen-Agent framework dla zaawansowanej orkiestracji
    - Monitorowanie zadań w czasie rzeczywistym
    - Kolejka zadań z priorytetami

Uruchomienie:
    python3 webui.py --port 8080
    
Tryb klaster:
    python3 webui.py --cluster --nodes 6 --mode serial

Lub z poziomu pipeline.sh:
    ./pipeline.sh webui
"""

import os
import sys
import json
import subprocess
import threading
import socket
import hashlib
import time
import queue
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import html
import base64
import mimetypes

# ============================================================================
# KONFIGURACJA
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
TMP_DIR = os.path.join(SCRIPT_DIR, "tmp")
CHUNK_DIR = os.path.join(SCRIPT_DIR, "chunk")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp")
CLUSTER_DIR = os.path.join(SCRIPT_DIR, "cluster")
TASKS_DIR = os.path.join(SCRIPT_DIR, "tasks")

DEFAULT_PORT = 8080
HOST = "0.0.0.0"

# Konfiguracja klastra
CLUSTER_CONFIG = {
    "enabled": False,
    "nodes": [],
    "mode": "serial",  # serial, parallel, hybrid
    "current_node": 0,
    "task_queue": [],
    "active_tasks": {},
    "completed_tasks": [],
    "failed_tasks": []
}

# Domyślna konfiguracja节点 dla Raspberry Pi
DEFAULT_RPI_NODES = [
    {"id": "rpi4-1", "type": "rpi4", "host": "192.168.1.101", "port": 8080, "cores": 4, "ram": "4GB/8GB"},
    {"id": "rpi4-2", "type": "rpi4", "host": "192.168.1.102", "port": 8080, "cores": 4, "ram": "4GB/8GB"},
    {"id": "rpi4-3", "type": "rpi4", "host": "192.168.1.103", "port": 8080, "cores": 4, "ram": "4GB/8GB"},
    {"id": "rpi1-1", "type": "rpi1", "host": "192.168.1.104", "port": 8080, "cores": 1, "ram": "512MB"},
    {"id": "rpi1-2", "type": "rpi1", "host": "192.168.1.105", "port": 8080, "cores": 1, "ram": "512MB"},
    {"id": "rpi1-3", "type": "rpi1", "host": "192.168.1.106", "port": 8080, "cores": 1, "ram": "512MB"},
]

# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================


def ensure_directories():
    """Tworzy niezbędne katalogi jeśli nie istnieją."""
    for directory in [INPUT_DIR, TMP_DIR, CHUNK_DIR, OUTPUT_DIR, LOGS_DIR, TEMP_DIR, CLUSTER_DIR, TASKS_DIR]:
        os.makedirs(directory, exist_ok=True)


# ============================================================================
# FUNKCJE KLASTRA I ORKIESTRACJI (Qwen-Agent inspired)
# ============================================================================

def init_cluster_config():
    """Inicjalizuje konfigurację klastra z domyślnymi节点 Raspberry Pi."""
    CLUSTER_CONFIG["nodes"] = DEFAULT_RPI_NODES.copy()
    CLUSTER_CONFIG["enabled"] = True
    save_cluster_config()


def save_cluster_config():
    """Zapisuje konfigurację klastra do pliku JSON."""
    config_path = os.path.join(CLUSTER_DIR, "cluster_config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(CLUSTER_CONFIG, f, indent=2, ensure_ascii=False)


def load_cluster_config():
    """Ładuje konfigurację klastra z pliku JSON."""
    config_path = os.path.join(CLUSTER_DIR, "cluster_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                CLUSTER_CONFIG.update(loaded_config)
                return True
        except Exception:
            pass
    return False


def create_task(task_type, data, priority=5, target_node=None):
    """
    Tworzy nowe zadanie w systemie.
    
    Args:
        task_type: Typ zadania (convert, chunk, rewrite, assemble, upload)
        data: Dane zadania (np. nazwa pliku, parametry)
        priority: Priorytet 1-10 (1=najwyższy)
        target_node: ID node'a docelowego lub None dla auto-selection
    
    Returns:
        task_id: Unikalny identyfikator zadania
    """
    task_id = str(uuid.uuid4())[:8]
    task = {
        "id": task_id,
        "type": task_type,
        "data": data,
        "priority": priority,
        "target_node": target_node,
        "assigned_node": None,
        "status": "pending",  # pending, running, completed, failed
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "logs": []
    }
    
    # Dodaj do kolejki zadań
    CLUSTER_CONFIG["task_queue"].append(task)
    # Sortuj według priorytetu
    CLUSTER_CONFIG["task_queue"].sort(key=lambda x: (x["priority"], x["created_at"]))
    
    save_task_to_file(task)
    save_cluster_config()
    
    return task_id


def save_task_to_file(task):
    """Zapisuje zadanie do pliku JSON w TASKS_DIR."""
    task_path = os.path.join(TASKS_DIR, f"task_{task['id']}.json")
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def get_all_tasks():
    """Pobiera wszystkie zadania z TASKS_DIR."""
    tasks = []
    if not os.path.exists(TASKS_DIR):
        return tasks
    
    for filename in os.listdir(TASKS_DIR):
        if filename.startswith("task_") and filename.endswith(".json"):
            filepath = os.path.join(TASKS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    tasks.append(json.load(f))
            except Exception:
                continue
    
    return sorted(tasks, key=lambda x: (x.get("priority", 5), x.get("created_at", "")))


def update_task_status(task_id, status, result=None, error=None):
    """Aktualizuje status zadania."""
    task_path = os.path.join(TASKS_DIR, f"task_{task_id}.json")
    if not os.path.exists(task_path):
        return False
    
    try:
        with open(task_path, 'r+', encoding='utf-8') as f:
            task = json.load(f)
            task["status"] = status
            if status == "running":
                task["started_at"] = datetime.now().isoformat()
            elif status in ["completed", "failed"]:
                task["completed_at"] = datetime.now().isoformat()
            if result:
                task["result"] = result
            if error:
                task["error"] = error
            
            f.seek(0)
            f.truncate()
            json.dump(task, f, indent=2, ensure_ascii=False)
        
        # Aktualizuj też w pamięci
        for i, t in enumerate(CLUSTER_CONFIG["task_queue"]):
            if t["id"] == task_id:
                CLUSTER_CONFIG["task_queue"][i] = task
                break
        
        return True
    except Exception:
        return False


def assign_task_to_node(task_id, node_id):
    """Przypisuje zadanie do konkretnego node'a."""
    task_path = os.path.join(TASKS_DIR, f"task_{task_id}.json")
    if not os.path.exists(task_path):
        return False
    
    try:
        with open(task_path, 'r+', encoding='utf-8') as f:
            task = json.load(f)
            task["assigned_node"] = node_id
            f.seek(0)
            f.truncate()
            json.dump(task, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_node_stats(node_id):
    """Pobiera statystyki dla konkretnego node'a."""
    tasks = get_all_tasks()
    assigned = [t for t in tasks if t.get("assigned_node") == node_id]
    
    return {
        "node_id": node_id,
        "total_tasks": len(assigned),
        "completed": len([t for t in assigned if t["status"] == "completed"]),
        "failed": len([t for t in assigned if t["status"] == "failed"]),
        "pending": len([t for t in assigned if t["status"] == "pending"]),
        "running": len([t for t in assigned if t["status"] == "running"])
    }


def process_task_serial(task):
    """
    Przetwarza zadanie w trybie szeregowym na lokalnym node.
    Inspiracja: Qwen-Agent sequential execution pattern.
    """
    task_id = task["id"]
    task_type = task["type"]
    data = task.get("data", {})
    
    update_task_status(task_id, "running")
    
    try:
        if task_type == "convert":
            # Konwersja plików
            args = []
            if data.get("verbose"):
                args.append("-v")
            result = run_script("convert_to_txt.sh", args if args else None)
            
        elif task_type == "chunk":
            # Chunking
            filename = data.get("filename", "")
            chunk_size = str(data.get("chunk_size", 4096))
            file_path = os.path.join(TMP_DIR, filename)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Plik nie istnieje: {filename}")
            args = ['-s', chunk_size, '-o', CHUNK_DIR, file_path]
            result = run_script("chunk_script.sh", args)
            
        elif task_type == "rewrite":
            # Przepisywanie AI
            result = run_script("rewrite_chunks.sh")
            
        elif task_type == "assemble":
            # Składanie książki
            result = run_script("pipeline.sh", ["cli", "--assemble"])
            
        elif task_type == "upload":
            # Upload do Moodle
            result = run_script("upload_to_moodle.sh")
            
        else:
            result = {"success": False, "error": f"Nieznany typ zadania: {task_type}"}
        
        if result.get("success"):
            update_task_status(task_id, "completed", result=result)
        else:
            update_task_status(task_id, "failed", error=result.get("error", "Unknown error"))
            
    except Exception as e:
        update_task_status(task_id, "failed", error=str(e))


def execute_cluster_pipeline(mode="serial"):
    """
    Wykonuje pipeline na klastrze w wybranym trybie.
    
    Tryby:
        - serial: Zadania przetwarzane jedno po drugim (RPi1 -> RPi4 -> RPi1...)
        - parallel: Wszystkie node'y pracują równolegle
        - hybrid: RPi4 przetwarzają równolegle, RPi1 szeregowo
    """
    tasks = [t for t in CLUSTER_CONFIG["task_queue"] if t["status"] == "pending"]
    
    if not tasks:
        return {"success": False, "error": "Brak oczekujących zadań"}
    
    nodes = CLUSTER_CONFIG["nodes"]
    results = []
    
    if mode == "serial":
        # Tryb szeregowy - idealny dla heterogenicznego klastra
        for task in tasks:
            # Wybierz następny node w kolejności (round-robin)
            node_idx = CLUSTER_CONFIG["current_node"] % len(nodes)
            node = nodes[node_idx]
            
            assign_task_to_node(task["id"], node["id"])
            process_task_serial(task)
            
            CLUSTER_CONFIG["current_node"] = node_idx + 1
            results.append({"task_id": task["id"], "node": node["id"], "status": task["status"]})
            
    elif mode == "parallel":
        # Tryb równoległy - wszystkie node'y pracują jednocześnie
        with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
            future_to_task = {}
            
            for i, task in enumerate(tasks):
                if i < len(nodes):
                    node = nodes[i % len(nodes)]
                    assign_task_to_node(task["id"], node["id"])
                    future = executor.submit(process_task_serial, task)
                    future_to_task[future] = task
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    future.result()
                    results.append({"task_id": task["id"], "status": "completed"})
                except Exception as e:
                    results.append({"task_id": task["id"], "status": "failed", "error": str(e)})
    
    save_cluster_config()
    return {"success": True, "results": results}


def get_file_size(filepath):
    """Zwraca rozmiar pliku w formacie czytelnym dla człowieka."""
    try:
        size = os.path.getsize(filepath)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except OSError:
        return "N/A"


def count_files(directory):
    """Zlicza pliki w katalogu."""
    if not os.path.exists(directory):
        return 0
    return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])


def list_files(directory):
    """Zwraca listę plików w katalogu z metadanymi."""
    if not os.path.exists(directory):
        return []
    
    files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            files.append({
                "name": filename,
                "size": get_file_size(filepath),
                "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S'),
                "path": filepath
            })
    
    return sorted(files, key=lambda x: x["name"])


def read_log_file(log_name, lines=100):
    """Odczytuje ostatnie linie z pliku logu."""
    log_path = os.path.join(LOGS_DIR, log_name)
    if not os.path.exists(log_path):
        return []
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            return all_lines[-lines:]
    except Exception as e:
        return [f"Błąd odczytu logu: {e}\n"]


def run_script(script_name, args=None, background=False):
    """Uruchamia skrypt bash i zwraca wynik."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    
    if not os.path.exists(script_path):
        return {"success": False, "error": f"Skrypt nie istnieje: {script_name}"}
    
    cmd = ["bash", script_path]
    if args:
        cmd.extend(args)
    
    try:
        if background:
            # Uruchomienie w tle
            subprocess.Popen(cmd, cwd=SCRIPT_DIR, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            return {"success": True, "message": "Proces uruchomiony w tle"}
        else:
            result = subprocess.run(cmd, cwd=SCRIPT_DIR, 
                                  capture_output=True, text=True, timeout=300)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Przekroczono limit czasu wykonania (5 min)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_dependencies():
    """Sprawdza dostępne zależności systemowe."""
    deps = {}
    tools = {
        "curl": "curl --version",
        "jq": "jq --version",
        "pandoc": "pandoc --version",
        "pdftotext": "pdftotext -v"
    }
    
    for tool, cmd in tools.items():
        try:
            result = subprocess.run(cmd.split(), capture_output=True, timeout=5)
            deps[tool] = {
                "installed": result.returncode == 0,
                "version": result.stdout.decode('utf-8', errors='ignore').split('\n')[0] if result.returncode == 0 else "N/A"
            }
        except Exception:
            deps[tool] = {"installed": False, "version": "N/A"}
    
    return deps


def load_config():
    """Ładuje konfigurację z pliku config.sh."""
    config_path = os.path.join(SCRIPT_DIR, "config.sh")
    config = {"exists": False, "variables": {}}
    
    if os.path.exists(config_path):
        config["exists"] = True
        try:
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config["variables"][key.strip()] = value.strip().strip('"\'')
        except Exception:
            pass
    
    return config


def get_pipeline_status():
    """Zwraca aktualny status pipeline."""
    # Załaduj konfigurację klastra
    load_cluster_config()
    
    return {
        "directories": {
            "input": {"count": count_files(INPUT_DIR), "exists": os.path.exists(INPUT_DIR)},
            "tmp": {"count": count_files(TMP_DIR), "exists": os.path.exists(TMP_DIR)},
            "chunk": {"count": count_files(CHUNK_DIR), "exists": os.path.exists(CHUNK_DIR)},
            "output": {"count": count_files(OUTPUT_DIR), "exists": os.path.exists(OUTPUT_DIR)},
            "logs": {"count": count_files(LOGS_DIR), "exists": os.path.exists(LOGS_DIR)},
            "cluster": {"count": count_files(CLUSTER_DIR), "exists": os.path.exists(CLUSTER_DIR)},
            "tasks": {"count": count_files(TASKS_DIR), "exists": os.path.exists(TASKS_DIR)}
        },
        "dependencies": check_dependencies(),
        "config": load_config(),
        "cluster": {
            "enabled": CLUSTER_CONFIG["enabled"],
            "nodes_count": len(CLUSTER_CONFIG["nodes"]),
            "nodes": CLUSTER_CONFIG["nodes"],
            "mode": CLUSTER_CONFIG["mode"],
            "task_queue_length": len(CLUSTER_CONFIG["task_queue"]),
            "active_tasks": len([t for t in CLUSTER_CONFIG["task_queue"] if t.get("status") == "running"]),
            "completed_tasks": len([t for t in CLUSTER_CONFIG["task_queue"] if t.get("status") == "completed"]),
            "failed_tasks": len([t for t in CLUSTER_CONFIG["task_queue"] if t.get("status") == "failed"])
        }
    }


# ============================================================================
# GENEROWANIE HTML
# ============================================================================


def generate_html_page(title, content, active_tab="dashboard"):
    """Generuje kompletną stronę HTML."""
    
    tabs = {
        "dashboard": "Dashboard",
        "files": "Pliki",
        "convert": "Konwersja",
        "chunking": "Chunking",
        "rewrite": "Przepisywanie",
        "cluster": "Klaster",
        "logs": "Logi",
        "settings": "Ustawienia"
    }
    
    nav_items = ""
    for tab_id, tab_name in tabs.items():
        active_class = "active" if tab_id == active_tab else ""
        nav_items += f'<a href="/?tab={tab_id}" class="nav-item {active_class}">{tab_name}</a>'
    
    html_template = f'''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - Book Rewriting Pipeline</title>
    <style>
        :root {{
            --primary-color: #4a90d9;
            --secondary-color: #357abd;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --bg-color: #f5f7fa;
            --card-bg: #ffffff;
            --text-color: #333333;
            --border-color: #e1e4e8;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        header {{
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 30px 0;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        header h1 {{
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        header p {{
            text-align: center;
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        nav {{
            background: var(--card-bg);
            padding: 15px 0;
            margin-bottom: 30px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            border-radius: 8px;
        }}
        
        .nav-container {{
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 10px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .nav-item {{
            padding: 12px 24px;
            text-decoration: none;
            color: var(--text-color);
            border-radius: 6px;
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        
        .nav-item:hover {{
            background-color: var(--primary-color);
            color: white;
        }}
        
        .nav-item.active {{
            background-color: var(--primary-color);
            color: white;
        }}
        
        .card {{
            background: var(--card-bg);
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        
        .card h2 {{
            color: var(--primary-color);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border-color);
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .stat-card h3 {{
            font-size: 2.5em;
            margin-bottom: 5px;
        }}
        
        .stat-card p {{
            opacity: 0.9;
        }}
        
        .btn {{
            display: inline-block;
            padding: 12px 24px;
            background-color: var(--primary-color);
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            font-size: 1em;
            transition: all 0.3s ease;
            margin-right: 10px;
            margin-bottom: 10px;
        }}
        
        .btn:hover {{
            background-color: var(--secondary-color);
            transform: translateY(-2px);
        }}
        
        .btn-success {{
            background-color: var(--success-color);
        }}
        
        .btn-success:hover {{
            background-color: #218838;
        }}
        
        .btn-warning {{
            background-color: var(--warning-color);
            color: #333;
        }}
        
        .btn-danger {{
            background-color: var(--danger-color);
        }}
        
        .btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            background-color: var(--bg-color);
            font-weight: 600;
        }}
        
        tr:hover {{
            background-color: var(--bg-color);
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        
        .status-success {{
            background-color: #d4edda;
            color: #155724;
        }}
        
        .status-error {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        
        .status-warning {{
            background-color: #fff3cd;
            color: #856404;
        }}
        
        .log-output {{
            background-color: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
        }}
        
        .progress-bar {{
            width: 100%;
            height: 30px;
            background-color: var(--bg-color);
            border-radius: 15px;
            overflow: hidden;
            margin: 15px 0;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
        }}
        
        .alert {{
            padding: 15px 20px;
            border-radius: 6px;
            margin-bottom: 20px;
        }}
        
        .alert-info {{
            background-color: #d1ecf1;
            color: #0c5460;
            border-left: 4px solid #17a2b8;
        }}
        
        .alert-success {{
            background-color: #d4edda;
            color: #155724;
            border-left: 4px solid var(--success-color);
        }}
        
        .alert-warning {{
            background-color: #fff3cd;
            color: #856404;
            border-left: 4px solid var(--warning-color);
        }}
        
        .alert-error {{
            background-color: #f8d7da;
            color: #721c24;
            border-left: 4px solid var(--danger-color);
        }}
        
        .form-group {{
            margin-bottom: 20px;
        }}
        
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        
        .form-control {{
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 1em;
        }}
        
        .checkbox-group {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .checkbox-group input[type="checkbox"] {{
            width: 20px;
            height: 20px;
        }}
        
        pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        
        @media (max-width: 768px) {{
            .nav-container {{
                flex-direction: column;
            }}
            
            .grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>📚 Book Rewriting Pipeline</h1>
        <p>System przepisywania książek z wykorzystaniem AI</p>
    </header>
    
    <div class="container">
        <nav>
            <div class="nav-container">
                {nav_items}
            </div>
        </nav>
        
        <main>
            {content}
        </main>
    </div>
    
    <script>
        // Auto-refresh dla logów
        function refreshLogs() {{
            const logOutput = document.getElementById('log-output');
            if (logOutput) {{
                fetch('/api/logs?action=refresh')
                    .then(r => r.json())
                    .then(data => {{
                        logOutput.innerHTML = data.content || '';
                        logOutput.scrollTop = logOutput.scrollHeight;
                    }});
            }}
        }}
        
        // Odświeżaj logi co 5 sekund
        setInterval(refreshLogs, 5000);
        
        // Obsługa formularzy AJAX
        document.querySelectorAll('form[data-ajax]').forEach(form => {{
            form.addEventListener('submit', function(e) {{
                e.preventDefault();
                
                const formData = new FormData(this);
                const actionUrl = this.action || this.getAttribute('data-action');
                
                fetch(actionUrl, {{
                    method: 'POST',
                    body: formData
                }})
                .then(r => r.json())
                .then(data => {{
                    if (data.success) {{
                        alert('✓ ' + data.message);
                        location.reload();
                    }} else {{
                        alert('✗ Błąd: ' + data.error);
                    }}
                }})
                .catch(err => alert('Błąd: ' + err));
            }});
        }});
    </script>
</body>
</html>'''
    
    return html_template


def generate_dashboard_content():
    """Generuje zawartość dashboardu."""
    status = get_pipeline_status()
    
    dirs = status["directories"]
    deps = status["dependencies"]
    cluster = status.get("cluster", {})
    
    stats_html = f'''
    <div class="grid">
        <div class="stat-card">
            <h3>{dirs['input']['count']}</h3>
            <p>Pliki wejściowe</p>
        </div>
        <div class="stat-card">
            <h3>{dirs['tmp']['count']}</h3>
            <p>Pliki tymczasowe</p>
        </div>
        <div class="stat-card">
            <h3>{dirs['chunk']['count']}</h3>
            <p>Chunki</p>
        </div>
        <div class="stat-card">
            <h3>{dirs['output']['count']}</h3>
            <p>Wyniki</p>
        </div>
        <div class="stat-card" style="background: linear-gradient(135deg, #667eea, #764ba2);">
            <h3>{cluster.get('nodes_count', 0)}</h3>
            <p>Node'y klastra</p>
        </div>
        <div class="stat-card" style="background: linear-gradient(135deg, #f093fb, #f5576c);">
            <h3>{cluster.get('task_queue_length', 0)}</h3>
            <p>Zadania w kolejce</p>
        </div>
    </div>
    '''
    
    deps_html = "<h3>Dependencje</h3><table><tr><th>Narzędzie</th><th>Status</th><th>Wersja</th></tr>"
    for tool, info in deps.items():
        status_class = "status-success" if info["installed"] else "status-error"
        status_text = "✓ Zainstalowane" if info["installed"] else "✗ Brak"
        deps_html += f"<tr><td>{tool}</td><td><span class='status-badge {status_class}'>{status_text}</span></td><td>{html.escape(info['version'])}</td></tr>"
    deps_html += "</table>"
    
    config_info = ""
    if status["config"]["exists"]:
        config_info = "<div class='alert alert-success'>✓ Plik konfiguracyjny znaleziony</div>"
    else:
        config_info = "<div class='alert alert-warning'>⚠ Plik konfiguracyjny nie istnieje. Utwórz config.sh</div>"
    
    quick_actions = '''
    <h3>Szybkie akcje</h3>
    <div style="margin-top: 15px;">
        <a href="/?tab=convert" class="btn">🔄 Konwertuj pliki</a>
        <a href="/?tab=chunking" class="btn">📝 Podziel na chunki</a>
        <a href="/?tab=rewrite" class="btn">✍️ Przepisz chunki</a>
        <a href="/?tab=cluster" class="btn">🖥️ Zarządzaj klastrem</a>
        <a href="/?tab=files" class="btn">📁 Przeglądaj pliki</a>
    </div>
    '''
    
    content = f'''
    <div class="card">
        <h2>📊 Status systemu</h2>
        {stats_html}
    </div>
    
    <div class="card">
        <h2>⚙️ Konfiguracja</h2>
        {config_info}
    </div>
    
    <div class="card">
        {deps_html}
    </div>
    
    <div class="card">
        {quick_actions}
    </div>
    '''
    
    return content


def generate_files_content():
    """Generuje zawartość strony z plikami."""
    input_files = list_files(INPUT_DIR)
    tmp_files = list_files(TMP_DIR)
    chunk_files = list_files(CHUNK_DIR)
    output_files = list_files(OUTPUT_DIR)
    
    def file_table(files, empty_msg):
        if not files:
            return f"<p>{empty_msg}</p>"
        
        html_table = "<table><tr><th>Nazwa</th><th>Rozmiar</th><th>Zmodyfikowano</th></tr>"
        for f in files:
            html_table += f"<tr><td>{html.escape(f['name'])}</td><td>{f['size']}</td><td>{html.escape(f['modified'])}</td></tr>"
        html_table += "</table>"
        return html_table
    
    content = f'''
    <div class="card">
        <h2>📥 Pliki wejściowe (input/)</h2>
        <div class="alert alert-info">Umieść tutaj pliki do przetworzenia (.doc, .docx, .pdf, .odt, .txt, .md)</div>
        {file_table(input_files, "Brak plików w katalogu input")}
    </div>
    
    <div class="card">
        <h2>📄 Pliki tymczasowe (tmp/)</h2>
        {file_table(tmp_files, "Brak przekonwertowanych plików")}
    </div>
    
    <div class="card">
        <h2>🧩 Chunki (chunk/)</h2>
        {file_table(chunk_files, "Brak chunków")}
    </div>
    
    <div class="card">
        <h2>📤 Wyniki (output/)</h2>
        {file_table(output_files, "Brak wyników")}
    </div>
    '''
    
    return content


def generate_convert_content():
    """Generuje zawartość strony konwersji."""
    input_files = list_files(INPUT_DIR)
    
    files_options = ""
    for f in input_files:
        files_options += f"<option value='{html.escape(f['name'])}'>{html.escape(f['name'])}</option>"
    
    if not files_options:
        files_options = "<option disabled>Brak plików w katalogu input</option>"
    
    content = f'''
    <div class="card">
        <h2>🔄 Konwersja plików do formatu TXT</h2>
        
        <div class="alert alert-info">
            Skrypt convert_to_txt.sh konwertuje pliki z katalogu input na format .txt do katalogu tmp.
            Obsługiwane formaty: .doc, .docx, .pdf, .odt, .rtf, .html, .md
        </div>
        
        <form data-ajax data-action="/api/convert" method="POST">
            <div class="form-group">
                <label>Wybierz plik (lub zostaw dla wszystkich):</label>
                <select name="file" class="form-control">
                    <option value="">Wszystkie pliki</option>
                    {files_options}
                </select>
            </div>
            
            <div class="form-group checkbox-group">
                <input type="checkbox" id="verbose" name="verbose" value="true">
                <label for="verbose">Tryb szczegółowy (-v)</label>
            </div>
            
            <div class="form-group checkbox-group">
                <input type="checkbox" id="force" name="force" value="true">
                <label for="force">Nadpisz istniejące pliki (--force)</label>
            </div>
            
            <button type="submit" class="btn btn-success">▶️ Rozpocznij konwersję</button>
        </form>
        
        <div style="margin-top: 20px;">
            <h3>Instrukcja</h3>
            <ol style="margin-left: 20px; margin-top: 10px;">
                <li>Umieść pliki do konwersji w katalogu <code>input/</code></li>
                <li>Wybierz konkretny plik lub pozostaw domyślne ustawienie dla wszystkich</li>
                <li>Kliknij "Rozpocznij konwersję"</li>
                <li>Przekonwertowane pliki pojawią się w katalogu <code>tmp/</code></li>
            </ol>
        </div>
    </div>
    '''
    
    return content


def generate_chunking_content():
    """Generuje zawartość strony chunkingu."""
    tmp_files = list_files(TMP_DIR)
    
    files_options = ""
    for f in tmp_files:
        if f['name'].endswith('.txt'):
            files_options += f"<option value='{html.escape(f['name'])}'>{html.escape(f['name'])}</option>"
    
    if not files_options:
        files_options = "<option disabled>Brak plików .txt w katalogu tmp</option>"
    
    content = f'''
    <div class="card">
        <h2>🧩 Dzielenie na chunki</h2>
        
        <div class="alert alert-info">
            Skrypt chunk_script.sh dzieli pliki tekstowe na mniejsze segmenty (chunki) 
            o wielkości ~4096 tokenów każdy. Każdy chunk zawiera metadane JSON.
        </div>
        
        <form data-ajax data-action="/api/chunk" method="POST">
            <div class="form-group">
                <label>Wybierz plik do podziału:</label>
                <select name="file" class="form-control" required>
                    <option value="">-- Wybierz plik --</option>
                    {files_options}
                </select>
            </div>
            
            <div class="form-group">
                <label>Rozmiar chunka (tokeny):</label>
                <input type="number" name="chunk_size" class="form-control" value="4096" min="512" max="8192">
            </div>
            
            <button type="submit" class="btn btn-success">▶️ Podziel na chunki</button>
        </form>
        
        <div style="margin-top: 20px;">
            <h3>Struktura chunków</h3>
            <p>Każdy chunk zawiera metadane z następującymi informacjami:</p>
            <ul style="margin-left: 20px; margin-top: 10px;">
                <li><code>chunk_id</code> - unikalny identyfikator</li>
                <li><code>token_count</code> - liczba tokenów</li>
                <li><code>previous_chunk</code> / <code>next_chunk</code> - linki do sąsiednich chunków</li>
                <li><code>chapter</code> / <code>subsection</code> - informacje o strukturze</li>
                <li><code>content</code> - przetworzony tekst</li>
            </ul>
        </div>
    </div>
    '''
    
    return content


def generate_rewrite_content():
    """Generuje zawartość strony przepisywania."""
    chunk_files = [f for f in list_files(CHUNK_DIR) if f['name'].endswith(('.txt', '.json'))]
    
    chunk_count = len(chunk_files)
    
    content = f'''
    <div class="card">
        <h2>✍️ Przepisywanie chunków z AI</h2>
        
        <div class="alert alert-info">
            Skrypt rewrite_chunks.sh wykorzystuje modele AI Qwen do przepisywania treści:
            <br>• <strong>qwen-coder</strong> - analiza struktury i formatowania
            <br>• <strong>qwen3.6-35B-A3B</strong> - głęboka analiza i przepisanie tekstu
        </div>
        
        <div class="alert {'alert-success' if chunk_count > 0 else 'alert-warning'}">
            {'✓' if chunk_count > 0 else '⚠'} Znaleziono chunków do przetworzenia: <strong>{chunk_count}</strong>
        </div>
        
        <form data-ajax data-action="/api/rewrite" method="POST">
            <div class="form-group">
                <label>Tryb przetwarzania:</label>
                <select name="mode" class="form-control">
                    <option value="all">Wszystkie chunki</option>
                    <option value="single">Pojedynczy chunk (wybierz poniżej)</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Wybierz chunk (dla trybu pojedynczego):</label>
                <select name="chunk" class="form-control">
                    <option value="">-- Wybierz chunk --</option>
                    {"".join(f"<option value='{html.escape(f['name'])}'>{html.escape(f['name'])}</option>" for f in chunk_files)}
                </select>
            </div>
            
            <button type="submit" class="btn btn-success" {'disabled' if chunk_count == 0 else ''}>▶️ Rozpocznij przepisywanie</button>
        </form>
        
        <div style="margin-top: 20px;">
            <h3>Wymagania</h3>
            <ul style="margin-left: 20px; margin-top: 10px;">
                <li>Skonfigurowany plik <code>config.sh</code> z kluczami API</li>
                <li>Dostęp do endpointów modeli Qwen</li>
                <li>Chunki w katalogu <code>chunk/</code></li>
            </ul>
        </div>
    </div>
    '''
    
    return content


def generate_logs_content():
    """Generuje zawartość strony z logami."""
    log_files = list_files(LOGS_DIR)
    
    log_options = ""
    selected_log = "pipeline.log"
    for f in log_files:
        selected = "selected" if f['name'] == selected_log else ""
        log_options += f"<option value='{html.escape(f['name'])}' {selected}>{html.escape(f['name'])}</option>"
    
    if not log_options:
        log_options = "<option disabled>Brak plików logów</option>"
    
    log_content = "".join(read_log_file(selected_log)) if log_files else "Brak logów do wyświetlenia"
    
    content = f'''
    <div class="card">
        <h2>📋 Logi systemu</h2>
        
        <div class="form-group">
            <label>Wybierz plik logu:</label>
            <select id="log-select" class="form-control" onchange="loadLog(this.value)">
                {log_options}
            </select>
        </div>
        
        <div style="margin-bottom: 15px;">
            <button onclick="refreshLogs()" class="btn">🔄 Odśwież</button>
            <button onclick="downloadLog()" class="btn">💾 Pobierz</button>
        </div>
        
        <div class="log-output" id="log-output">
            <pre>{html.escape(log_content)}</pre>
        </div>
    </div>
    
    <script>
        function loadLog(filename) {{
            fetch('/api/logs?file=' + encodeURIComponent(filename))
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('log-output').innerHTML = '<pre>' + data.content + '</pre>';
                }});
        }}
        
        function downloadLog() {{
            const filename = document.getElementById('log-select').value;
            window.location.href = '/api/logs/download?file=' + encodeURIComponent(filename);
        }}
    </script>
    '''
    
    return content


def generate_settings_content():
    """Generuje zawartość strony ustawień."""
    config = load_config()
    deps = check_dependencies()
    load_cluster_config()
    
    config_vars = ""
    common_vars = [
        ("QWEN_API_KEY", "Klucz API Qwen", ""),
        ("QWEN_AGENT_URL", "URL agenta Qwen", "http://localhost:8000/v1/chat/completions"),
        ("QWEN_CODER_URL", "URL codera Qwen", "http://localhost:8000/v1/chat/completions"),
        ("QWEN_LARGE_MODEL_URL", "URL dużego modelu", "http://localhost:8000/v1/chat/completions"),
        ("MAX_TOKENS", "Maksymalna liczba tokenów", "4096"),
        ("TEMPERATURE", "Temperatura (kreatywność)", "0.7")
    ]
    
    for var_name, description, default in common_vars:
        current_value = config["variables"].get(var_name, default)
        is_password = "password" in var_name.lower() or "key" in var_name.lower()
        input_type = "password" if is_password else "text"
        config_vars += f'''
        <div class="form-group">
            <label title="{html.escape(description)}">{html.escape(var_name)}</label>
            <input type="{input_type}" name="{html.escape(var_name)}" class="form-control" 
                   value="{html.escape(current_value)}" placeholder="{html.escape(default)}">
            <small style="color: #666;">{html.escape(description)}</small>
        </div>
        '''
    
    # Konfiguracja klastra
    cluster_config_html = ""
    if CLUSTER_CONFIG["enabled"]:
        nodes_html = ""
        for node in CLUSTER_CONFIG["nodes"]:
            nodes_html += f'''
            <tr>
                <td>{html.escape(node['id'])}</td>
                <td>{html.escape(node['type'])}</td>
                <td>{html.escape(node['host'])}:{node['port']}</td>
                <td>{node['cores']} cores</td>
                <td>{html.escape(node['ram'])}</td>
            </tr>
            '''
        
        cluster_config_html = f'''
        <div class="card">
            <h3>🖥️ Konfiguracja Klastra Raspberry Pi</h3>
            <p>Tryb pracy: <strong>{CLUSTER_CONFIG['mode']}</strong></p>
            <table>
                <tr><th>ID Node'a</th><th>Typ</th><th>Adres</th><th>Rdzenie</th><th>RAM</th></tr>
                {nodes_html}
            </table>
            <form data-ajax data-action="/api/cluster/init" method="POST" style="margin-top: 15px;">
                <button type="submit" class="btn btn-warning">🔄 Zresetuj konfigurację klastra</button>
            </form>
        </div>
        '''
    
    content = f'''
    <div class="card">
        <h2>⚙️ Konfiguracja API</h2>
        
        <div class="alert alert-info">
            Edytuj plik <code>config.sh</code> aby skonfigurować parametry API i inne ustawienia.
        </div>
        
        <form data-ajax data-action="/api/config" method="POST">
            {config_vars}
            
            <button type="submit" class="btn btn-success">💾 Zapisz konfigurację</button>
        </form>
    </div>
    
    {cluster_config_html}
    
    <div class="card">
        <h2>🔍 Sprawdzenie zależności</h2>
        <table>
            <tr><th>Narzędzie</th><th>Status</th><th>Wersja</th></tr>
            {"".join(f"<tr><td>{tool}</td><td>{'✓' if info['installed'] else '✗'}</td><td>{html.escape(info['version'])}</td></tr>" for tool, info in deps.items())}
        </table>
    </div>
    
    <div class="card">
        <h2>📁 Katalogi</h2>
        <table>
            <tr><th>Katalog</th><th>Ścieżka</th><th>Liczba plików</th></tr>
            <tr><td>Input</td><td><code>{html.escape(INPUT_DIR)}</code></td><td>{count_files(INPUT_DIR)}</td></tr>
            <tr><td>Tmp</td><td><code>{html.escape(TMP_DIR)}</code></td><td>{count_files(TMP_DIR)}</td></tr>
            <tr><td>Chunk</td><td><code>{html.escape(CHUNK_DIR)}</code></td><td>{count_files(CHUNK_DIR)}</td></tr>
            <tr><td>Output</td><td><code>{html.escape(OUTPUT_DIR)}</code></td><td>{count_files(OUTPUT_DIR)}</td></tr>
            <tr><td>Logs</td><td><code>{html.escape(LOGS_DIR)}</code></td><td>{count_files(LOGS_DIR)}</td></tr>
            <tr><td>Cluster</td><td><code>{html.escape(CLUSTER_DIR)}</code></td><td>{count_files(CLUSTER_DIR)}</td></tr>
            <tr><td>Tasks</td><td><code>{html.escape(TASKS_DIR)}</code></td><td>{count_files(TASKS_DIR)}</td></tr>
        </table>
    </div>
    '''
    
    return content


def generate_cluster_content():
    """Generuje zawartość strony zarządzania klastrem."""
    load_cluster_config()
    tasks = get_all_tasks()
    
    # Statystyki node'ów
    nodes_stats_html = ""
    for node in CLUSTER_CONFIG["nodes"]:
        stats = get_node_stats(node["id"])
        status_class = "status-success" if stats["running"] == 0 else "status-warning"
        
        nodes_stats_html += f'''
        <div class="card" style="border-left: 4px solid {'#4a90d9' if node['type'] == 'rpi4' else '#f5576c'};">
            <h3>{html.escape(node['id'])} - {html.escape(node['type'].upper())}</h3>
            <p><strong>Adres:</strong> {html.escape(node['host'])}:{node['port']}</p>
            <p><strong>Rdzenie:</strong> {node['cores']} | <strong>RAM:</strong> {html.escape(node['ram'])}</p>
            <div class="grid" style="margin-top: 15px;">
                <div class="stat-card" style="padding: 10px; font-size: 0.9em;">
                    <h4 style="font-size: 1.5em;">{stats['completed']}</h4>
                    <p>Zakończone</p>
                </div>
                <div class="stat-card" style="padding: 10px; font-size: 0.9em; background: #ffc107;">
                    <h4 style="font-size: 1.5em;">{stats['running']}</h4>
                    <p>Uruchomione</p>
                </div>
                <div class="stat-card" style="padding: 10px; font-size: 0.9em; background: #dc3545;">
                    <h4 style="font-size: 1.5em;">{stats['failed']}</h4>
                    <p>Błędne</p>
                </div>
            </div>
        </div>
        '''
    
    # Lista zadań
    tasks_html = "<h3>Wszystkie zadania</h3><table><tr><th>ID</th><th>Typ</th><th>Priorytet</th><th>Status</th><th>Node</th><th>Utworzono</th></tr>"
    for task in tasks[:50]:  # Limit 50 najnowszych
        status_class = {
            "pending": "status-warning",
            "running": "status-success",
            "completed": "status-success",
            "failed": "status-error"
        }.get(task.get("status", "pending"), "status-warning")
        
        tasks_html += f'''
        <tr>
            <td><code>{html.escape(task['id'])}</code></td>
            <td>{html.escape(task['type'])}</td>
            <td>{task.get('priority', 5)}</td>
            <td><span class="status-badge {status_class}">{html.escape(task.get('status', 'unknown'))}</span></td>
            <td>{html.escape(task.get('assigned_node', '-')) or '-'}</td>
            <td>{html.escape(task.get('created_at', '-')[:19])}</td>
        </tr>
        '''
    tasks_html += "</table>"
    
    content = f'''
    <div class="card">
        <h2>🖥️ Klaster Raspberry Pi (3x RPi4 + 3x RPi1)</h2>
        <div class="alert alert-info">
            <strong>Tryb szeregowy:</strong> Zadania przetwarzane są jedno po drugim, przechodząc przez wszystkie node'y w kolejności round-robin.
            Idealne dla heterogenicznego sprzętu gdzie RPi1 mogą obsługiwać lżejsze zadania.
        </div>
        <div class="alert alert-success">
            <strong>Inspiracja Qwen-Agent:</strong> System wykorzystuje wzorce sekwencyjnego wykonania z frameworka Qwen-Agent,
            zapewniając niezawodne przetwarzanie nawet na słabszym sprzęcie.
        </div>
    </div>
    
    <div class="card">
        <h3>📊 Status Node'ów</h3>
        <div class="grid">
            {nodes_stats_html}
        </div>
    </div>
    
    <div class="card">
        <h3>📋 Kolejka Zadań</h3>
        <form data-ajax data-action="/api/cluster/create-task" method="POST" style="margin-bottom: 20px;">
            <div class="grid">
                <div class="form-group">
                    <label>Typ zadania</label>
                    <select name="task_type" class="form-control">
                        <option value="convert">Konwersja plików</option>
                        <option value="chunk">Chunking</option>
                        <option value="rewrite">Przepisywanie AI</option>
                        <option value="assemble">Składanie książki</option>
                        <option value="upload">Upload do Moodle</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Priorytet (1-10)</label>
                    <input type="number" name="priority" class="form-control" min="1" max="10" value="5">
                </div>
            </div>
            <button type="submit" class="btn btn-success">➕ Dodaj zadanie</button>
        </form>
        {tasks_html}
    </div>
    
    <div class="card">
        <h3>▶️ Uruchom Pipeline</h3>
        <form data-ajax data-action="/api/cluster/execute" method="POST">
            <div class="form-group">
                <label>Tryb wykonania</label>
                <select name="mode" class="form-control">
                    <option value="serial">Serial (szeregowy) - zalecany</option>
                    <option value="parallel">Parallel (równoległy)</option>
                </select>
            </div>
            <button type="submit" class="btn btn-success">▶️ Uruchom przetwarzanie</button>
        </form>
    </div>
    '''
    
    return content


# ============================================================================
# OBSŁUGA ŻĄDAŃ HTTP
# ============================================================================


class WebUIHandler(SimpleHTTPRequestHandler):
    """Handler HTTP dla WebUI."""
    
    def do_GET(self):
        """Obsługuje żądania GET."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        if path == "/" or path == "/index.html":
            self.handle_dashboard(query)
        elif path.startswith("/api/"):
            self.handle_api(query)
        else:
            super().do_GET()
    
    def do_POST(self):
        """Obsługuje żądania POST."""
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        if path == "/api/convert":
            self.handle_convert(post_data)
        elif path == "/api/chunk":
            self.handle_chunk(post_data)
        elif path == "/api/rewrite":
            self.handle_rewrite(post_data)
        elif path == "/api/config":
            self.handle_config(post_data)
        elif path == "/api/full-pipeline":
            self.handle_full_pipeline(post_data)
        elif path == "/api/cluster/init":
            self.handle_cluster_init(post_data)
        elif path == "/api/cluster/create-task":
            self.handle_cluster_create_task(post_data)
        elif path == "/api/cluster/execute":
            self.handle_cluster_execute(post_data)
        else:
            self.send_error(404, "Not Found")
    
    def send_json_response(self, data):
        """Wysyła odpowiedź JSON."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def handle_dashboard(self, query):
        """Generuje stronę główną."""
        tab = query.get('tab', ['dashboard'])[0]
        
        content_generators = {
            'dashboard': generate_dashboard_content,
            'files': generate_files_content,
            'convert': generate_convert_content,
            'chunking': generate_chunking_content,
            'rewrite': generate_rewrite_content,
            'cluster': generate_cluster_content,
            'logs': generate_logs_content,
            'settings': generate_settings_content
        }
        
        content_func = content_generators.get(tab, generate_dashboard_content)
        content = content_func()
        
        html_content = generate_html_page("Dashboard", content, tab)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def handle_api(self, query):
        """Obsługuje endpointy API."""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/status":
            self.send_json_response(get_pipeline_status())
        elif path == "/api/logs":
            action = query.get('action', ['view'])[0]
            filename = query.get('file', ['pipeline.log'])[0]
            
            if action == "download":
                log_path = os.path.join(LOGS_DIR, filename)
                if os.path.exists(log_path):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                    self.end_headers()
                    with open(log_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404, "Log file not found")
            else:
                content = "".join(read_log_file(filename))
                self.send_json_response({"content": content})
        else:
            self.send_error(404, "API endpoint not found")
    
    def handle_convert(self, post_data):
        """Obsługuje konwersję plików."""
        params = parse_qs(post_data)
        
        args = []
        if params.get('verbose', [''])[0]:
            args.append('-v')
        if params.get('force', [''])[0]:
            args.append('-F')
        
        result = run_script('convert_to_txt.sh', args if args else None)
        
        self.send_json_response({
            "success": result.get("success", False),
            "message": "Konwersja zakończona" if result.get("success") else "Błąd konwersji",
            "output": result.get("stdout", "")[:1000] if result.get("stdout") else ""
        })
    
    def handle_chunk(self, post_data):
        """Obsługuje dzielenie na chunki."""
        params = parse_qs(post_data)
        
        filename = params.get('file', [''])[0]
        chunk_size = params.get('chunk_size', ['4096'])[0]
        
        if not filename:
            self.send_json_response({"success": False, "error": "Nie wybrano pliku"})
            return
        
        file_path = os.path.join(TMP_DIR, filename)
        if not os.path.exists(file_path):
            self.send_json_response({"success": False, "error": f"Plik nie istnieje: {filename}"})
            return
        
        args = ['-s', chunk_size, '-o', CHUNK_DIR, file_path]
        result = run_script('chunk_script.sh', args)
        
        self.send_json_response({
            "success": result.get("success", False),
            "message": "Chunking zakończony" if result.get("success") else "Błąd chunkingu",
            "output": result.get("stdout", "")[:1000] if result.get("stdout") else ""
        })
    
    def handle_rewrite(self, post_data):
        """Obsługuje przepisywanie chunków."""
        params = parse_qs(post_data)
        
        mode = params.get('mode', ['all'])[0]
        
        result = run_script('rewrite_chunks.sh')
        
        self.send_json_response({
            "success": result.get("success", False),
            "message": "Przepisywanie zakończone" if result.get("success") else "Błąd przepisywania",
            "output": result.get("stdout", "")[:1000] if result.get("stdout") else ""
        })
    
    def handle_config(self, post_data):
        """Obsługuje zapis konfiguracji."""
        params = parse_qs(post_data)
        
        config_path = os.path.join(SCRIPT_DIR, "config.sh")
        
        try:
            with open(config_path, 'w') as f:
                f.write("#!/bin/bash\n")
                f.write("# Konfiguracja Book Rewriting Pipeline\n")
                f.write(f"# Wygenerowano: {datetime.now().isoformat()}\n\n")
                
                for key, values in params.items():
                    if values[0]:
                        f.write(f'{key}="{values[0]}"\n')
            
            self.send_json_response({"success": True, "message": "Konfiguracja zapisana"})
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)})
    
    def handle_full_pipeline(self, post_data):
        """Obsługuje uruchomienie pełnego pipeline."""
        result = run_script('pipeline.sh', ['cli', '--all'])
        
        self.send_json_response({
            "success": result.get("success", False),
            "message": "Pipeline zakończony" if result.get("success") else "Błąd pipeline",
            "output": result.get("stdout", "")[:1000] if result.get("stdout") else ""
        })
    
    def handle_cluster_init(self, post_data):
        """Inicjalizuje konfigurację klastra."""
        try:
            init_cluster_config()
            self.send_json_response({
                "success": True,
                "message": "Konfiguracja klastra zainicjalizowana (6 node'ów: 3x RPi4 + 3x RPi1)"
            })
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)})
    
    def handle_cluster_create_task(self, post_data):
        """Tworzy nowe zadanie w kolejce klastra."""
        params = parse_qs(post_data)
        
        task_type = params.get('task_type', ['convert'])[0]
        priority = int(params.get('priority', [5])[0])
        
        # Dane zadania zależne od typu
        data = {
            "verbose": True,
            "filename": params.get('filename', [''])[0],
            "chunk_size": int(params.get('chunk_size', [4096])[0])
        }
        
        try:
            task_id = create_task(task_type, data, priority=priority)
            self.send_json_response({
                "success": True,
                "message": f"Zadanie utworzone: {task_id}",
                "task_id": task_id
            })
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)})
    
    def handle_cluster_execute(self, post_data):
        """Wykonuje pipeline na klastrze."""
        params = parse_qs(post_data)
        mode = params.get('mode', ['serial'])[0]
        
        try:
            # Upewnij się że klaster jest zainicjalizowany
            if not CLUSTER_CONFIG["nodes"]:
                init_cluster_config()
            
            result = execute_cluster_pipeline(mode=mode)
            self.send_json_response(result)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)})
    
    def log_message(self, format, *args):
        """Tłumienie logów serwera HTTP."""
        pass


# ============================================================================
# GŁÓWNA FUNKCJA
# ============================================================================


def find_free_port(start_port=DEFAULT_PORT):
    """Znajduje wolny port począwszy od start_port."""
    port = start_port
    while port < start_port + 100:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((HOST, port))
            sock.close()
            return port
        except OSError:
            port += 1
    raise RuntimeError("Nie można znaleźć wolnego portu")


def main():
    """Główna funkcja uruchamiająca WebUI."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Book Rewriting Pipeline - WebUI')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Port serwera (domyślnie: {DEFAULT_PORT})')
    parser.add_argument('--host', type=str, default=HOST, help=f'Adres hosta (domyślnie: {HOST})')
    args = parser.parse_args()
    
    # Upewnij się, że katalogi istnieją
    ensure_directories()
    
    # Znajdź wolny port jeśli domyślny jest zajęty
    port = args.port
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((args.host, port))
        sock.close()
    except OSError:
        port = find_free_port(args.port)
        print(f"Port {args.port} zajęty, używam portu {port}")
    
    server_address = (args.host, port)
    httpd = HTTPServer(server_address, WebUIHandler)
    
    print("=" * 60)
    print("📚 Book Rewriting Pipeline - WebUI")
    print("=" * 60)
    print(f"Serwer uruchomiony na: http://{args.host}:{port}")
    print(f"Katalog roboczy: {SCRIPT_DIR}")
    print("=" * 60)
    print("Dostępne zakładki:")
    print("  • Dashboard - przegląd systemu")
    print("  • Pliki - zarządzanie plikami")
    print("  • Konwersja - konwersja do TXT")
    print("  • Chunking - dzielenie na chunki")
    print("  • Przepisywanie - AI rewriting")
    print("  • Logi - podgląd logów")
    print("  • Ustawienia - konfiguracja")
    print("=" * 60)
    print("Naciśnij Ctrl+C aby zatrzymać serwer")
    print("=" * 60)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nZatrzymywanie serwera...")
        httpd.shutdown()
        print("Serwer zatrzymany.")


if __name__ == "__main__":
    main()
