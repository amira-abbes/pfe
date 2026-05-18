import requests
import json

def test_ollama_direct():
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": "qwen2.5:3b",
        "prompt": "Say hello in French",
        "stream": False
    }
    try:
        print("Sending request to Ollama (3B)...")
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json().get('response')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ollama_direct()
