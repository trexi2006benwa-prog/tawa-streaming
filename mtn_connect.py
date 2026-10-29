import requests
import json

# Your verified primary key
PRIMARY_KEY = "6e2387d598d04d25b0ec25a6c4983ae4"
USER_ID = "3c2a1e4b-5d6f-47a8-b9c0-e1f2a3b4c5d6"

def run_connection():
    try:
        print("🔄 Step 1: Registering user on MTN Sandbox...")
        
        register_url = "https://mtn.com"
        register_headers = {
            "X-Reference-Id": USER_ID,
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
        }
        
        register_body = json.dumps({
            "providerCallbackHost": "https://webhook.site"
        })
        
        register_res = requests.post(register_url, data=register_body, headers=register_headers)
        
        # FIXED: Corrected the syntax here to handle both 200 and 201 statuses safely
        if register_res.status_code in:
            print("✅ Step 1 complete! User registered profile.")
        else:
            print(f"⚠️ Step 1 notification (Status {register_res.status_code})")

        print("🔄 Step 2: Requesting your secret API Key...")
        
        key_url = f"https://mtn.com/{USER_ID}/apikey"
        key_headers = {
            "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
            "Cache-Control": "no-cache"
        }
        
        key_res = requests.post(key_url, headers=key_headers)
        
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
            print(f"Raw body: {key_res.text[:200]}")

    except Exception as e:
        print(f"❌ Failed: {str(e)}")

if __name__ == "__main__":
    run_connection()
