#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Distributed AI Cluster Controller with Dynamic Load Balancing for LLMs.
Architecture:
- Master Node: Orchestrates tasks, balances LLM load across 3x RPi4, aggregates results.
- Worker Nodes (3x RPi4): Run local Qwen LLM. Handle tasks dynamically based on availability.
- Worker Nodes (3x RPi1): Scrape/Interact with Web AI (ChatGPT, Grok, Qwen Web).
- Final Step: Aggregate all data -> Send to Local LLM (if needed for final polish) -> Upload to Moodle.
"""

import json
import time
import requests
import threading
import queue
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
CONFIG_FILE = "config.json"

class ClusterConfig:
    def __init__(self, config_path: str):
        if not os.path.exists(config_path):
            self.create_default_config(config_path)
        
        with open(config_path, 'r') as f:
            self.data = json.load(f)
        
        self.master_ip = self.data.get('master', {}).get('ip', 'localhost')
        self.nodes = self.data.get('nodes', [])
        self.moodle_config = self.data.get('moodle', {})
        self.llm_config = self.data.get('local_llm', {})

    def create_default_config(self, path: str):
        default = {
            "master": {"ip": "192.168.1.100", "port": 5000},
            "moodle": {
                "url": "https://moodle.example.com",
                "token": "YOUR_MOODLE_TOKEN",
                "course_id": 1,
                "activity_id": 123 # Assignments ID
            },
            "local_llm": {"model": "Qwen/Qwen2.5-7B-Instruct", "max_context": 4096},
            "nodes": [
                # RPi 4 Cluster (LLM Workers)
                {"id": "rpi4-1", "type": "rpi4", "ip": "192.168.1.101", "port": 5001, "role": "llm_worker", "status": "idle"},
                {"id": "rpi4-2", "type": "rpi4", "ip": "192.168.1.102", "port": 5001, "role": "llm_worker", "status": "idle"},
                {"id": "rpi4-3", "type": "rpi4", "ip": "192.168.1.103", "port": 5001, "role": "llm_worker", "status": "idle"},
                # RPi 1 Cluster (Web AI Workers)
                {"id": "rpi1-1", "type": "rpi1", "ip": "192.168.1.104", "port": 5002, "role": "web_scraper", 
                 "credentials": {"email": "user1@example.com", "password": "pass1"}, 
                 "targets": ["chatgpt.com", "grok.com"]},
                {"id": "rpi1-2", "type": "rpi1", "ip": "192.168.1.105", "port": 5002, "role": "web_scraper", 
                 "credentials": {"email": "user2@example.com", "password": "pass2"}, 
                 "targets": ["coder.qwen.ai"]},
                {"id": "rpi1-3", "type": "rpi1", "ip": "192.168.1.106", "port": 5002, "role": "web_scraper", 
                 "credentials": {"email": "user3@example.com", "password": "pass3"}, 
                 "targets": ["chatgpt.com", "grok.com", "coder.qwen.ai"]}
            ]
        }
        with open(path, 'w') as f:
            json.dump(default, f, indent=4)
        print(f"Created default config at {path}")
        self.data = default
        self.nodes = default.get('nodes', [])

# --- Load Balancer for RPi4 LLMs ---
class LLMLoadBalancer:
    def __init__(self, nodes: List[Dict]):
        self.llm_nodes = [n for n in nodes if n.get('type') == 'rpi4' and n.get('role') == 'llm_worker']
        self.node_status = {n['id']: 'idle' for n in self.llm_nodes} # idle, busy
        self.lock = threading.Lock()
        print(f"[LoadBalancer] Initialized with {len(self.llm_nodes)} LLM workers.")

    def get_available_node(self) -> Optional[Dict]:
        """Returns the first available node and marks it as busy."""
        with self.lock:
            for node in self.llm_nodes:
                if self.node_status[node['id']] == 'idle':
                    self.node_status[node['id']] = 'busy'
                    return node
        return None

    def mark_node_idle(self, node_id: str):
        """Marks a node as idle after task completion."""
        with self.lock:
            if node_id in self.node_status:
                self.node_status[node_id] = 'idle'
                print(f"[LoadBalancer] Node {node_id} is now idle.")

    def process_chunk(self, node: Dict, chunk_data: Dict) -> Dict:
        """Sends data to specific RPi4 for LLM processing."""
        url = f"http://{node['ip']}:{node['port']}/process"
        try:
            response = requests.post(url, json=chunk_data, timeout=300) # Long timeout for LLM
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}", "node": node['id']}
        except Exception as e:
            return {"error": str(e), "node": node['id']}
        finally:
            self.mark_node_idle(node['id'])

# --- Web AI Handler (RPi1) ---
class WebAIHandler:
    def __init__(self, node: Dict):
        self.node = node
        self.session = requests.Session()
        
    def login_and_scrape(self, query: str) -> Dict:
        """Simulates login and scraping on Web AI platforms."""
        results = []
        creds = self.node.get('credentials', {})
        targets = self.node.get('targets', [])
        
        print(f"[WebAI] Node {self.node['id']} logging in as {creds.get('email')}...")
        
        # Simulate Login (In real scenario, use Selenium/Playwright on RPi1)
        # Here we assume the RPi1 endpoint handles the browser automation
        for target in targets:
            payload = {
                "query": query,
                "email": creds.get('email'),
                "password": creds.get('password'),
                "target_site": target
            }
            url = f"http://{self.node['ip']}:{self.node['port']}/scrape"
            try:
                resp = requests.post(url, json=payload, timeout=120)
                if resp.status_code == 200:
                    results.append(resp.json())
                else:
                    results.append({"source": target, "error": "Failed to scrape"})
            except Exception as e:
                results.append({"source": target, "error": str(e)})
        
        return {"node_id": self.node['id'], "results": results}

# --- Master Controller ---
class ClusterMaster:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config = ClusterConfig(config_path)
        self.lb = LLMLoadBalancer(self.config.nodes)
        self.web_nodes = [n for n in self.config.nodes if n.get('type') == 'rpi1']
        self.results_store = {}
        
    def chunk_file(self, file_path: str, chunk_size: int = 1000) -> List[Dict]:
        """Reads a file and splits it into chunks with metadata."""
        chunks = []
        if not os.path.exists(file_path):
            print(f"File {file_path} not found.")
            return chunks
            
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        total_len = len(text)
        for i in range(0, total_len, chunk_size):
            chunk_text = text[i:i+chunk_size]
            chunks.append({
                "id": hashlib.md5(chunk_text.encode()).hexdigest()[:8],
                "index": i // chunk_size,
                "content": chunk_text,
                "total_chunks": (total_len + chunk_size - 1) // chunk_size
            })
        print(f"[Master] Split file into {len(chunks)} chunks.")
        return chunks

    def distribute_llm_tasks(self, chunks: List[Dict]) -> List[Dict]:
        """Distributes chunks to RPi4 nodes dynamically."""
        results = []
        task_queue = queue.Queue()
        for chunk in chunks:
            task_queue.put(chunk)
        
        def worker():
            while not task_queue.empty():
                chunk = task_queue.get()
                node = None
                # Poll for available node
                while node is None:
                    node = self.lb.get_available_node()
                    if node is None:
                        time.sleep(0.5) # Wait if all busy
                
                print(f"[Master] Dispatching chunk {chunk['id']} to {node['id']}")
                res = self.lb.process_chunk(node, chunk)
                res['chunk_index'] = chunk['index']
                results.append(res)
                task_queue.task_done()

        # Use threads to manage distribution, but actual processing is limited by LB
        threads = []
        for _ in range(len(self.lb.llm_nodes)):
            t = threading.Thread(target=worker)
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
            
        return sorted(results, key=lambda x: x.get('chunk_index', 0))

    def distribute_web_tasks(self, query: str) -> List[Dict]:
        """Dispatches query to all RPi1 nodes for Web AI scraping."""
        results = []
        with ThreadPoolExecutor(max_workers=len(self.web_nodes)) as executor:
            futures = []
            for node in self.web_nodes:
                handler = WebAIHandler(node)
                futures.append(executor.submit(handler.login_and_scrape, query))
            
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({"error": str(e)})
        return results

    def aggregate_and_finalize(self, llm_results: List[Dict], web_results: List[Dict], output_file: str):
        """Aggregates all results, optionally runs final LLM pass, saves to file."""
        print("[Master] Aggregating results...")
        
        full_text_parts = []
        
        # Process LLM Results (Ordered Chunks)
        for res in llm_results:
            if 'result' in res:
                full_text_parts.append(res['result'])
            elif 'error' in res:
                full_text_parts.append(f"[Error in chunk from {res.get('node', 'unknown')}: {res['error']}]")
        
        # Process Web Results
        web_summary = "\n--- WEB AI INSIGHTS ---\n"
        for res in web_results:
            node_id = res.get('node_id', 'unknown')
            for item in res.get('results', []):
                source = item.get('source', 'unknown')
                content = item.get('content', item.get('error', 'No content'))
                web_summary += f"[{node_id} via {source}]: {content}\n"
        
        combined_text = "\n".join(full_text_parts) + "\n" + web_summary
        
        # Optional: Final Polish by sending aggregated text back to ONE free LLM node
        print("[Master] Running final aggregation pass on LLM...")
        final_prompt = {
            "prompt": f"Połącz i podsumuj poniższy tekst, usuwając błędy i tworząc spójną całość:\n\n{combined_text}",
            "max_tokens": 2048
        }
        
        final_node = None
        while final_node is None:
            final_node = self.lb.get_available_node()
            if final_node is None:
                time.sleep(0.5)
        
        final_res = self.lb.process_chunk(final_node, {"content": final_prompt['prompt'], "id": "final_aggregation"})
        
        final_output = final_res.get('result', combined_text)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_output)
        
        print(f"[Master] Final output saved to {output_file}")
        return final_output

    def upload_to_moodle(self, file_path: str):
        """Uploads the final file to Moodle Assignment."""
        moodle = self.config.moodle_config
        if not moodle.get('url'):
            print("[Moodle] Configuration missing, skipping upload.")
            return

        print(f"[Moodle] Uploading {file_path} to {moodle['url']}...")
        
        # Moodle API logic (simplified)
        # 1. Get file content
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'text/plain')}
            data = {
                'id': moodle.get('activity_id'),
                'token': moodle.get('token')
            }
            
            try:
                # This is a placeholder for the actual Moodle API call (mod_assign_submit_assignment_file)
                # Real implementation requires specific Moodle Web Service function
                url = f"{moodle['url']}/webservice/upload.php" 
                # response = requests.post(url, data=data, files=files)
                
                # Simulation for demonstration
                time.sleep(1)
                print("[Moodle] Upload successful (simulated).")
                return True
            except Exception as e:
                print(f"[Moodle] Upload failed: {e}")
                return False

    def run_pipeline(self, input_file: str, output_file: str = "final_result.txt"):
        """Executes the full pipeline."""
        print("=== Starting Distributed AI Pipeline ===")
        
        # 1. Chunking
        chunks = self.chunk_file(input_file)
        if not chunks:
            return

        # 2. Parallel Execution: LLM Processing (RPi4) & Web Scraping (RPi1)
        print("Starting parallel processing...")
        
        # Thread for LLM distribution
        llm_thread = threading.Thread(target=lambda: setattr(self, '_llm_res', self.distribute_llm_tasks(chunks)))
        
        # Thread for Web Scraping (using a summary or first chunk as query context)
        query_context = chunks[0]['content'][:500] + "..." if chunks else "Analyze this topic."
        web_thread = threading.Thread(target=lambda: setattr(self, '_web_res', self.distribute_web_tasks(query_context)))
        
        llm_thread.start()
        web_thread.start()
        
        llm_thread.join()
        web_thread.join()
        
        llm_results = getattr(self, '_llm_res', [])
        web_results = getattr(self, '_web_res', [])
        
        # 3. Aggregation & Final LLM Pass
        final_text = self.aggregate_and_finalize(llm_results, web_results, output_file)
        
        # 4. Moodle Upload
        self.upload_to_moodle(output_file)
        
        print("=== Pipeline Completed ===")

# --- CLI Entry Point ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cluster AI Master Controller")
    parser.add_argument("--file", type=str, required=True, help="Input file to process")
    parser.add_argument("--output", type=str, default="result.txt", help="Output file path")
    parser.add_argument("--config", type=str, default=CONFIG_FILE, help="Config file path")
    
    args = parser.parse_args()
    
    master = ClusterMaster(args.config)
    master.run_pipeline(args.file, args.output)
