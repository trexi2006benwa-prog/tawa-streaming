const axios = require('axios');

// Using your official primary key and a fresh User ID
const PRIMARY_KEY = "6e2387d598d04d25b0ec25a6c4983ae4"; 
const USER_ID = "3c2a1e4b-5d6f-47a8-b9c0-e1f2a3b4c5d6"; 

async function runConnection() {
  try {
    console.log('🔄 Step 1: Registering user on MTN Sandbox...');
    await axios.post(
      'https://mtn.com',
      { providerCallbackHost: 'https://webhook.site' },
      {
        headers: {
          'X-Reference-Id': USER_ID,
          'Ocp-Apim-Subscription-Key': PRIMARY_KEY,
          'Content-Type': 'application/json'
        }
      }
    );

    console.log('✅ Step 1 complete! User registered.');
    console.log('🔄 Step 2: Requesting your secret API Key...');

    const response = await axios.post(
      `https://mtn.com/${USER_ID}/apikey`,
      {},
      { headers: { 'Ocp-Apim-Subscription-Key': PRIMARY_KEY } }
    );

    console.log('\n=========================================');
    console.log('🎉 SUCCESS! APPs LINKED TO MTN');
    console.log('=========================================');
    console.log(`API User ID: ${USER_ID}`);
    console.log(`API Key:     ${response.data.apiKey}`);
    console.log('=========================================');

  } catch (error) {
    console.error('❌ Failed:', error.response ? error.response.data : error.message);
  }
}

runConnection();
