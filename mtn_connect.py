import os
import uuid
import requests
from requests.auth import HTTPBasicAuth

# 1. Credentials Setup
# Tries to pull from Render Environment Variables first; falls back to your screenshot values
PRIMARY_KEY = os.environ.get("MTN_PRIMARY_KEY", "6f1febfcbb6543da88fba810d1fd1deb")
API_USER_ID = os.environ.get("MTN_API_USER_ID", "a9e2b104-c518-47bc-ad74-88899dfc4491")
API_KEY = os.environ.get("MTN_API_KEY", "2514135a636d47309eadb7284eb5ac10")

BASE_URL = "https://mtn.com"


def get_access_token():
    """Generates the required Bearer Token using Basic Auth credentials."""
    url = f"{BASE_URL}/collection/token/"
    headers = {
        "Ocp-Apim-Subscription-Key": PRIMARY_KEY
    }
    auth = HTTPBasicAuth(API_USER_ID, API_KEY)

    response = requests.post(url, headers=headers, auth=auth)
    response.raise_for_status()
    return response.json().get("access_token")


def initiate_payment(amount, phone_number, account_id):
    """Triggers the push notification prompt on the user's mobile wallet."""
    token = get_access_token()
    url = f"{BASE_URL}/collection/v1_0/requesttopay"
    
    # Generate a unique transaction tracking reference code
    transaction_reference = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Reference-Id": transaction_reference,
        "X-Target-Environment": "sandbox",
        "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "amount": str(amount),
        "currency": "EUR",  # Sandbox requires EUR configuration
        "externalId": str(account_id),  # Your custom app database tracking reference
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": str(phone_number)  # Zambian format matching country code (e.g., 26097...)
        },
        "payerMessage": "Subscription to TAWA Streaming",
        "payeeNote": "TAWA Streaming Premium"
    }

    response = requests.post(url, headers=headers, json=payload)

    # 202 Accepted means the USSD pop-up has been pushed to the customer device successfully
    if response.status_code == 202:
        print(f"✅ MoMo prompt sent successfully! ID: {transaction_reference}")
        return transaction_reference
    else:
        raise Exception(f"MTN API Error: {response.text}")


def check_payment_status(transaction_id):
    """Checks the explicit state of an active transaction ID profile."""
    token = get_access_token()
    url = f"{BASE_URL}/collection/v1_0/requesttopay/{transaction_id}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Target-Environment": "sandbox",
        "Ocp-Apim-Subscription-Key": PRIMARY_KEY,
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    # Returns: 'PENDING', 'SUCCESSFUL', or 'FAILED'
    return response.json().get("status")
