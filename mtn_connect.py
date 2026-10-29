import requests
import json

PRIMARY_KEY = "6e2387d598d04d25b0ec25a6c4983ae4"
USER_ID = "3c2a1e4b-5d6f-47a8-b9c0-e1f2a3b4c5d6"

def run_connection():
    try:
        print("🔄 Step 1: Verifying registration...")
        register_url = "https://mtn.com"
        register_headers = {
            "X-Reference-Id": USER_ID,
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json"
        }
        register_body = json.dumps({"providerCallbackHost": "https://webhook.site"})
        register_res = requests.post(register_url, data=register_body, headers=register_headers)
        
        print(f"📋 Step 1 Status: {register_res.status_code}")

        print("🔄 Step 2: Requesting API Key...")
        # Fixed URL: Clean, absolute path to the sandbox gateway
        key_url = f"https://mtn.com/{USER_ID}/apikey"
        key_headers = {
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
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
            print(f"API User ID: {USER_ID}")
            print(f"API Key:     {api_key}")
            print("=========================================")
        else:
            print(f"❌ Key extraction failed. Server Response Code: {key_res.status_code}")
            print(f"Raw body chunk: {key_res.text[:200]}")

    except Exception as e:
        print(f"❌ Failed: {str(e)}")

if __name__ == "__main__":
    run_connection()
