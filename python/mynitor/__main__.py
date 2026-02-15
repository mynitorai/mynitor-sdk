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
        print("Usage: python3 -m mynitor [ping|doctor|mock]")
        sys.exit(1)

    command = sys.argv[1]

    base_url = os.getenv("MYNITOR_API_URL", "https://app.mynitor.ai")

    if command == "doctor":
        version = "0.2.7" 
        print(f"🩺 MyNitor Doctor (v{version})")
        print("---------------------------")
        
        if not api_key:
            print("❌ API Key: Missing (MYNITOR_API_KEY not found in env)")
        else:
            prefix = api_key[:8]
            last4 = api_key[-4:]
            print(f"✅ API Key: Detected ({prefix}...{last4})")

        try:
            print("📡 Testing Connection...")
            endpoint = f"{base_url}/api/v1/onboarding/status"
            res = requests.get(endpoint, headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                print("✅ Connection: MyNitor Cloud is reachable")
                print(f"✅ Organization: {data.get('orgId', 'Verified')}")
            else:
                print(f"❌ Connection: API returned {res.status_code} ({res.reason})")
        except requests.exceptions.SSLError as e:
            print("❌ Connection: SSL Certificate Verification Failed")
            print(f"   Error details: {e}")
            print("   💡 Suggestion: This looks like an SSL issue. Check your certificate store or proxy.")
        except requests.exceptions.ConnectionError as e:
            print("❌ Connection: Failed to reach MyNitor Cloud")
            print(f"   Error details: {e}")
            print("   💡 Suggestion: Check your internet connection or DNS settings.")
        except Exception as e:
            print(f"❌ Connection: An unexpected error occurred")
            print(f"   Error: {e}")
        return

    if command == "mock":
        print("🎭 MyNitor: Sending mock OpenAI event to Cloud API...")
        endpoint = os.getenv("MYNITOR_API_URL", "https://app.mynitor.ai/api/v1/events")
        payload = {
            "event_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent": "mynitor-py-cli-mock",
            "workflow": "diagnostic-mock",
            "provider": "openai",
            "model": "gpt-4o",
            "input_tokens": 150,
            "output_tokens": 450,
            "latency_ms": 1200,
            "status": "success",
            "metadata": {"type": "diagnostic-mock"}
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=5)
            if response.status_code in [200, 201]:
                print("✅ Mock event sent successfully!")
                print("✨ Check your dashboard /events page to see the generated data.")
            else:
                print(f"❌ Failed: {response.status_code} {response.text}")
        except Exception as e:
            print(f"❌ Network Error: {e}")
        return

    if command == "ping":
        print("🚀 MyNitor: Sending verification signal to Cloud API...")
        
        endpoint = os.getenv("MYNITOR_API_URL", "https://app.mynitor.ai/api/v1/events")
        payload = {
            "event_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent": "mynitor-py-cli",
            "workflow": "onboarding-ping",
            "model": "ping-test",
            "input_tokens": 0,
            "output_tokens": 0,
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
