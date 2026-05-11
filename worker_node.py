#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker Node Server for Raspberry Pi Cluster.
Runs on both RPi4 (LLM Worker) and RPi1 (Web AI Scraper).
"""

import json
import os
import sys
from flask import Flask, request, jsonify
import threading
import time

app = Flask(__name__)

# Global state
NODE_CONFIG = {}
IS_BUSY = False
BUSY_LOCK = threading.Lock()

def load_config():
    global NODE_CONFIG
    config_file = "worker_config.json"
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            NODE_CONFIG = json.load(f)
    else:
        # Default config
        NODE_CONFIG = {
            "node_id": "unknown",
            "type": "rpi4",  # or "rpi1"
            "llm_model": "Qwen/Qwen2.5-7B-Instruct",
            "llm_port": 5001,
            "scrape_port": 5002
        }
        with open(config_file, 'w') as f:
            json.dump(NODE_CONFIG, f, indent=4)

# --- LLM Processing Endpoint (RPi4) ---
def process_with_local_llm(prompt: str) -> str:
    """
    Integrates with local LLM running on RPi4.
    Assumes LLM server is running on localhost:8080 (adjust as needed).
    """
    # Simulate LLM call - replace with actual API call to your local LLM server
    # Example for Ollama:
    # import requests
    # resp = requests.post('http://localhost:11434/api/generate', json={
    #     "model": "qwen2.5:7b",
    #     "prompt": prompt,
    #     "stream": False
    # })
    # return resp.json().get('response', '')
    
    print(f"[LLM] Processing chunk of length {len(prompt)}...")
    time.sleep(2)  # Simulate processing time
    
    # Mock response for testing
    return f"[Processed by {NODE_CONFIG.get('node_id')}] Analysis of: {prompt[:100]}..."

@app.route('/process', methods=['POST'])
def handle_process():
    global IS_BUSY
    data = request.json
    
    if not data or 'content' not in data:
        return jsonify({"error": "No content provided"}), 400
    
    with BUSY_LOCK:
        if IS_BUSY:
            return jsonify({"error": "Node is busy"}), 503
        IS_BUSY = True
    
    try:
        content = data['content']
        chunk_id = data.get('id', 'unknown')
        
        print(f"[{NODE_CONFIG.get('node_id')}] Received chunk {chunk_id}")
        
        result = process_with_local_llm(content)
        
        return jsonify({
            "chunk_id": chunk_id,
            "result": result,
            "node": NODE_CONFIG.get('node_id')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        with BUSY_LOCK:
            IS_BUSY = False

# --- Web Scraping Endpoint (RPi1) ---
def scrape_web_ai(query: str, email: str, password: str, target: str) -> dict:
    """
    Performs browser automation to interact with Web AI.
    Uses Selenium/Playwright (must be installed on RPi1).
    """
    print(f"[WebAI] Logging into {target} as {email}...")
    
    # Simulate browser automation
    # Real implementation would use:
    # from selenium import webdriver
    # driver = webdriver.Chrome()
    # driver.get(f"https://{target}")
    # ... login steps ...
    # ... send query ...
    # ... extract response ...
    
    time.sleep(3)  # Simulate network delay
    
    return {
        "source": target,
        "content": f"Response from {target} for query: {query[:50]}...",
        "timestamp": time.time()
    }

@app.route('/scrape', methods=['POST'])
def handle_scrape():
    data = request.json
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    query = data.get('query', '')
    email = data.get('email', '')
    password = data.get('password', '')
    target = data.get('target_site', '')
    
    if not all([query, email, password, target]):
        return jsonify({"error": "Missing required fields"}), 400
    
    print(f"[{NODE_CONFIG.get('node_id')}] Scraping {target}...")
    
    try:
        result = scrape_web_ai(query, email, password, target)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "source": target}), 500

# --- Health Check ---
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "node_id": NODE_CONFIG.get('node_id'),
        "status": "busy" if IS_BUSY else "idle",
        "type": NODE_CONFIG.get('type')
    })

if __name__ == '__main__':
    load_config()
    
    node_type = NODE_CONFIG.get('type', 'rpi4')
    port = NODE_CONFIG.get('llm_port', 5001) if node_type == 'rpi4' else NODE_CONFIG.get('scrape_port', 5002)
    
    print(f"Starting worker node {NODE_CONFIG.get('node_id')} ({node_type}) on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
