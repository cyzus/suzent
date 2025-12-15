#!/usr/bin/env python3
"""
API key management utility for Suzent.

Usage:
    python scripts/manage_api_keys.py generate [--count N]
    python scripts/manage_api_keys.py list
    python scripts/manage_api_keys.py add <key>
    python scripts/manage_api_keys.py remove <key_hash>
"""
import sys
import json
import secrets
import hashlib
from pathlib import Path
from typing import List, Dict


API_KEYS_FILE = Path("config/api_keys.json")


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def load_api_keys() -> Dict:
    """Load API keys from file."""
    if not API_KEYS_FILE.exists():
        return {"keys": []}
    
    with open(API_KEYS_FILE, 'r') as f:
        return json.load(f)


def save_api_keys(data: Dict):
    """Save API keys to file."""
    API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(API_KEYS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Set restrictive permissions
    API_KEYS_FILE.chmod(0o600)


def cmd_generate(count: int = 1):
    """Generate new API key(s)."""
    data = load_api_keys()
    
    print(f"Generating {count} API key(s)...")
    print()
    
    for i in range(count):
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        
        data["keys"].append({
            "hash": key_hash,
            "created_at": __import__('datetime').datetime.now().isoformat(),
            "name": f"key-{len(data['keys']) + 1}",
        })
        
        print(f"API Key #{i+1}:")
        print(f"  Key:  {api_key}")
        print(f"  Hash: {key_hash}")
        print()
        print("⚠️  Save this key! It won't be shown again.")
        print()
    
    save_api_keys(data)
    
    print(f"✅ {count} key(s) generated and saved to {API_KEYS_FILE}")
    print()
    print("Add to your .env file:")
    print(f'SUZENT_API_KEYS={",".join(k["hash"] for k in data["keys"])}')


def cmd_list():
    """List all API key hashes."""
    data = load_api_keys()
    
    if not data["keys"]:
        print("No API keys configured.")
        return
    
    print(f"API Keys ({len(data['keys'])} total):")
    print()
    
    for i, key_data in enumerate(data["keys"], 1):
        print(f"{i}. {key_data.get('name', 'unnamed')}")
        print(f"   Hash: {key_data['hash'][:16]}...")
        print(f"   Created: {key_data.get('created_at', 'unknown')}")
        print()


def cmd_add(api_key: str):
    """Add an existing API key."""
    data = load_api_keys()
    key_hash = hash_api_key(api_key)
    
    # Check if already exists
    if any(k["hash"] == key_hash for k in data["keys"]):
        print("❌ This API key already exists!")
        return
    
    data["keys"].append({
        "hash": key_hash,
        "created_at": __import__('datetime').datetime.now().isoformat(),
        "name": f"key-{len(data['keys']) + 1}",
    })
    
    save_api_keys(data)
    print(f"✅ API key added (hash: {key_hash[:16]}...)")


def cmd_remove(key_hash: str):
    """Remove an API key by hash."""
    data = load_api_keys()
    
    # Find and remove
    original_count = len(data["keys"])
    data["keys"] = [k for k in data["keys"] if not k["hash"].startswith(key_hash)]
    
    if len(data["keys"]) == original_count:
        print(f"❌ No key found with hash starting with: {key_hash}")
        return
    
    save_api_keys(data)
    print(f"✅ API key removed (hash: {key_hash[:16]}...)")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "generate":
        count = 1
        if len(sys.argv) > 2 and sys.argv[2] == "--count":
            count = int(sys.argv[3])
        cmd_generate(count)
    
    elif command == "list":
        cmd_list()
    
    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: manage_api_keys.py add <key>")
            sys.exit(1)
        cmd_add(sys.argv[2])
    
    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: manage_api_keys.py remove <key_hash>")
            sys.exit(1)
        cmd_remove(sys.argv[2])
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
