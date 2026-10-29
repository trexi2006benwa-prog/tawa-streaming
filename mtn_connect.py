import requests

PRIMARY_KEY = "6e2387d598d04d25b0ec25a6c4983ae4"
USER_ID = "3c2a1e4b-5d6f-47a8-b9c0-e1f2a3b4c5d6"

def run_connection():
    try:
        print("🔄 Step 1: Registering user on MTN Sandbox...")
        register_url = "https://mtn.com"
        register_headers = {
            "X-Reference-Id": USER_ID,
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json"
        }
        register_body = {
            "providerCallbackHost": "https://webhook.site"
        }
        
        register_res = requests.post(register_url, json=register_body, headers=register_headers)
        
        if register_res.status_code == 201:
            print("✅ Step 1 complete! User registered.")
        else:
            print(f"⚠️ Step 1 warning (Status {register_res.status_code}): {register_res.text}")

        print("🔄 Step 2: Requesting your secret API Key...")
        key_url = f"https://mtn.com/{USER_ID}/apikey"
        key_headers = {
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY
        }
        
        key_res = requests.post(key_url, headers=key_headers)
        key_data = key_res.json()

        print("\n=========================================")
        print("🎉 SUCCESS! YOUR PYTHON APP IS LINKED TO MTN")
        print("=========================================")
        print(f"API User ID: {USER_ID}")
        print(f"API Key:     {key_data.get('apiKey')}")
        print("=========================================")

    except Exception as e:
        print(f"❌ Failed: {str(e)}")

if __name__ == "__main__":
    run_connection()
