import os
import sys
import requests
from datetime import datetime
from . import init

def run():
    api_key = os.getenv("MYNITOR_API_KEY")
    if not api_key:
        print("❌ Error: MYNITOR_API_KEY environment variable is not set.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python3 -m mynitor ping")
        sys.exit(1)

    command = sys.argv[1]

    if command == "ping":
        print("🚀 MyNitor: Sending verification signal to Cloud API...")
        
        endpoint = os.getenv("MYNITOR_API_URL", "https://app.mynitor.ai/api/v1/events")
        payload = {
            "event_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent": "mynitor-py-cli",
            "workflow": "onboarding-ping",
            "status": "success",
            "metadata": {"source": "py-cli-ping"}
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=5)
            if response.status_code == 200 or response.status_code == 201:
                print("✅ Connection verified! Event sent to MyNitor Cloud.")
                print("✨ Check your onboarding dashboard for the green checkmark.")
            else:
                print(f"❌ Failed to send event: {response.status_code} {response.reason}")
                print(f"Response: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Network Error: Could not reach MyNitor Cloud.")
            print(e)
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python3 -m mynitor ping")

if __name__ == "__main__":
    run()
