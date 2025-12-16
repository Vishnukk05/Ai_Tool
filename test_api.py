import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

print(f"--- TESTING API CONNECTION ---")
print(f"Key loaded: {api_key[:5]}...{api_key[-4:] if api_key else 'None'}")

if not api_key:
    print("❌ ERROR: No API Key found.")
    exit()

genai.configure(api_key=api_key)

# Try the stable model first
model_name = 'gemini-2.0-flash' 

try:
    print(f"\n--> Trying to talk to {model_name}...")
    model = genai.GenerativeModel(model_name)
    response = model.generate_content("Say hello")
    print(f"✅ SUCCESS! The AI replied: {response.text}")
except Exception as e:
    print(f"❌ ERROR: {e}")
    print("\n--- DIAGNOSIS ---")
    if "429" in str(e):
        print("You are being rate-limited. Wait 5 minutes and try again.")
    elif "403" in str(e) or "API key not valid" in str(e):
        print("Your API Key is invalid. Get a new one at aistudio.google.com")
    elif "not found" in str(e):
        print(f"Model {model_name} does not exist for your account.")