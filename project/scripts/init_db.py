# Database Initialization Script
# Run this to create tables and seed default settings

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from project.db.models import init_db, seed_default_settings, DEFAULT_SETTINGS
from project.db.crypto import TokenEncryption

def main():
    print("Initializing database...")
    
    # Create data directory
    os.makedirs("./data", exist_ok=True)
    
    # Initialize database
    session = init_db("sqlite:///./data/empire.db")
    
    # Seed default settings
    seed_default_settings(session)
    print("Default settings seeded.")
    
    # Verify tables created
    from sqlmodel import select
    from project.db.models import Campaign, system_settings_table
    
    settings_count = len(session.exec(select(system_settings_table)).all())
    print(f"Settings in DB: {settings_count}")
    
    # Test encryption
    try:
        encryption = TokenEncryption()
        test_token = "test_access_token_12345"
        encrypted = encryption.encrypt(test_token)
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == test_token
        print("Token encryption: OK")
    except Exception as e:
        print(f"Token encryption test failed: {e}")
        print("Make sure TOKEN_ENCRYPTION_PASSWORD and TOKEN_ENCRYPTION_SALT are set in environment")
    
    session.close()
    print("Database initialization complete!")

if __name__ == "__main__":
    main()