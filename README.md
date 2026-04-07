# Comix Wallet

https://github.com/user-attachments/assets/0a576bf6-13d2-45cb-85c6-458103d8f8c7

## Advanced imagery crypto wallet, baked inside discord.

### SEND FEATURE NOT IMPLEMENTED.

Use Solana and Litecoin in this wallet. You can send or recieve crypto. It has a beautiful dashboard and market activity using a line chart with data from CoinGecko.
Easily send and recieve crypto through this wallet.

### Setup Guide!
What you need to selfhost this bot, all by yourself.
1.Make a discord bot at https://discord.com/developers/applications
2.Copy the token (you will need this later)
3. Make a supabase account, and paste in the Project URL (you can find this in Youtube tutorial), aswell as the supabase key, and your discord bot token in .env.
4. You can generate a key by making a temporary key.py and pasting this code and running it:
```
from cryptography.fernet import Fernet

# Generate a new key
key = Fernet.generate_key()
print("Generated Key:", key.decode())

# Initialize Fernet and encrypt/decrypt
f = Fernet(key)
message = b"Secret message"
encrypted = f.encrypt(message)
decrypted = f.decrypt(encrypted)

print("Decrypted:", decrypted.decode())
```
After you have that key, put it in .env.
5. You wont need a CoinGecko API Key, since there is a Free Public API, but if you want faster limits then use a API key.
6. Run pip install -r requirements.txt
7. Run main.py
8. If all is good, it should run, then invite the bot using OAuth!


AI was used for some errors, and main imagery of dashboard.

