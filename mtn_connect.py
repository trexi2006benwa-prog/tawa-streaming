import requests
import json
import uuid

# Your verified primary key
PRIMARY_KEY = "6e2387d598d04d25b0ec25a6c4983ae4"

def run_connection():
    try:
        # 1. Generate a completely fresh UUID v4 dynamically
        USER_ID = str(uuid.uuid4())
        print(f"🆔 Generated Fresh App User ID: {USER_ID}")
        
        print("🔄 Step 1: Registering new user profile on MTN Sandbox...")
        register_url = "https://sandbox.momodeveloper.mtn.com/v1_0/apiuser"
        
        register_headers = {
            "X-Reference-Id": USER_ID,
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json"
        }
        
        # FIXED: Using a pure standard IP host string to prevent payload syntax validation failures
        register_body = json.dumps({"providerCallbackHost": "127.0.0.1"})
        
        register_res = requests.post(register_url, data=register_body, headers=register_headers)
        print(f"📋 Step 1 Status: {register_res.status_code}")
        
        if register_res.status_code != 201:
            print(f"⚠️ Step 1 did not return a 201 Created status. Response text snippet: {register_res.text[:200]}")

        print("🔄 Step 2: Requesting your secret API Key...")
        key_url = f"https://mtn.com{USER_ID}/apikey"
        key_headers = {
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json"
        }
        
        key_res = requests.post(key_url, headers=key_headers, data="{}")
        
        try:
            key_data = key_res.json()
            api_key = key_data.get('apiKey')
        except:
            api_key = None
            
        if api_key:
            print("\n=========================================")
            print("🎉 SUCCESS! YOUR PYTHON APP IS LINKED TO MTN")
            print("=========================================")
            print(f"API User ID (Save this): {USER_ID}")
            print(f"API Key (Save this):     {api_key}")
            print("=========================================")
        else:
            print(f"❌ Key extraction failed. Server Response Code: {key_res.status_code}")
            print(f"Raw body chunk: {key_res.text[:200]}")

    except Exception as e:
        print(f"❌ Failed: {str(e)}")

if __name__ == "__main__":
    run_connection()
