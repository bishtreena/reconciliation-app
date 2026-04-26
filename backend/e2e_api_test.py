import requests
import json
import sys
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
PLATFORM_CSV = SAMPLE_DIR / "platform_transactions.csv"
BANK_CSV = SAMPLE_DIR / "bank_settlements.csv"

def run_e2e():
    print("1. Uploading CSVs...")
    with open(PLATFORM_CSV, 'rb') as fp, open(BANK_CSV, 'rb') as fb:
        files = {
            'platform': ('platform.csv', fp, 'text/csv'),
            'bank': ('bank.csv', fb, 'text/csv')
        }
        res = requests.post(f"{BASE_URL}/upload", files=files)
    
    if res.status_code != 200:
        print(f"FAILED UPLOAD: {res.text}")
        sys.exit(1)
        
    run_id = res.json().get('run_id')
    print(f"   -> run_id: {run_id}")
    
    print(f"2. Reconciling run {run_id}...")
    res = requests.post(f"{BASE_URL}/reconcile/{run_id}")
    if res.status_code != 200:
        print(f"FAILED RECONCILE: {res.text}")
        sys.exit(1)
        
    print(f"3. Fetching results for run {run_id}...")
    res = requests.get(f"{BASE_URL}/results/{run_id}")
    if res.status_code != 200:
        print(f"FAILED GET RESULTS: {res.text}")
        sys.exit(1)
        
    data = res.json()
    print("================== FULL JSON RESPONSE ==================")
    print(json.dumps(data, indent=2))
    print("========================================================")

if __name__ == "__main__":
    run_e2e()
