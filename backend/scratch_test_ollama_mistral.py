import requests
import json

def test_ollama_direct():
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": "mistral-nemo:12b",
        "prompt": "Say hello in French",
        "stream": False
    }
    try:
        print("Sending request to Ollama (Mistral)...")
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json().get('response')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ollama_direct()
