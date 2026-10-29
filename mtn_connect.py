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
        register_url = "https://mtn.com"
        
        # Using normalized lowercase headers to guarantee gateway compatibility
        register_headers = {
            "x-reference-id": USER_ID,
            "ocp-apim-subscription-key": PRIMARY_KEY,
            "content-type": "application/json"
        }
        
        # Stripped "https://" protocol as required by MTN gateway validation specifications
        register_body = json.dumps({"providerCallbackHost": "webhook.site"})
        
        register_res = requests.post(register_url, data=register_body, headers=register_headers)
        print(f"📋 Step 1 Status: {register_res.status_code}")
        
        # If step 1 fails, we want to know exactly what the gateway complained about
        if register_res.status_code != 201:
            print(f"⚠️ Step 1 did not return a 201 Created status. Response text: {register_res.text}")

        print("🔄 Step 2: Requesting your secret API Key...")
        key_url = f"https://mtn.com/{USER_ID}/apikey"
        key_headers = {
            "ocp-apim-subscription-key": PRIMARY_KEY,
            "content-type": "application/json"
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
