# Mnemonic (Encrypted API Sync)

Suzent can encrypt your provider API keys before storing them in your GitHub sync repository, using a **BIP39 mnemonic phrase** — a sequence of 12 common English words — as the encryption secret. The phrase never leaves your devices; only ciphertext reaches GitHub.

Use this when you want provider API keys to follow your portable brain to another device **without** storing plaintext secrets on GitHub.

> **Terminology note:** The UI and some internal code still use the term "Shibboleth" for the passphrase/unlock state. The underlying secret is now a BIP39 mnemonic phrase rather than a freeform passphrase. The concepts are the same; only the format changed.

## When you need it

| Goal | Mnemonic required? |
|------|----------------------|
| Sync config, skills, markdown memory via GitHub | No |
| Sync API keys (OpenAI, Anthropic, etc.) via GitHub | Yes — enable **encrypted API sync** and use the same mnemonic on every device |

Encrypted API sync is **off by default**. You opt in under Settings → Data → GitHub Sync → **API Key Sync**.

## How it works (overview)

```
Mnemonic phrase (12 BIP39 words)
        │
        ▼
   scrypt (N=2^17, r=8, p=1, random 32-byte salt)
        │
        ▼
   32-byte AES-256-GCM key
        │
        ├──► Encrypt each API key from local keyring
        │         └──► ciphertext in bundles.json
        │
        └──► Push bundles.json to GitHub (inside suzent-sync/)
```

On another device, the same mnemonic derives the same key and decrypts bundles into that machine's local keyring.

## Setup (first device)

1. Complete [GitHub Sync Quick start](./README.md) so a profile and remote exist.
2. Open **API Key Sync** in the GitHub Sync card.
3. Click **Generate words** — Suzent generates a fresh 12-word BIP39 mnemonic.
4. **Write down or copy the phrase** — it cannot be recovered if lost.
5. Confirm the phrase and click **Enable**.
6. **Push** to GitHub — API keys are exported as ciphertext in `suzent-sync/_sync/secrets/bundles.json`.

The mnemonic is saved to the **OS keyring** after first use and auto-loaded on subsequent starts, so auto-sync works across restarts without manual unlock.

## Second device

1. Set up GitHub Sync on the new device with the same GitHub repo.
2. Open **API Key Sync** — Suzent detects the encrypted bundles in the pulled repo and prompts for the mnemonic.
3. Enter the **same mnemonic** and click **Register device**. This registers the device and imports the keys.
4. **Pull** — config, skills, memory, and API keys are all restored.

If the mnemonic is wrong, registration and import fail with an incorrect mnemonic error. Suzent cannot recover the keys without it.

## Mnemonic rotation

To change the mnemonic (e.g. if it may have been compromised):

1. Open **API Key Sync** on a trusted device.
2. Click **Rotate mnemonic** and generate or enter a new phrase.
3. Suzent re-encrypts all bundles with the new key and pushes new ciphertext.
4. All other devices must re-enter the new mnemonic when they next pull.

Rotation increments a `mnemonic_version` counter in `bundles.json`. When a device with an older version pulls, Suzent detects the mismatch and prompts for the new mnemonic automatically.

## Unlock and lock (session)

The mnemonic is cached in the running backend process (and the OS keyring) so you do not have to type it for every operation.

| State | Meaning |
|-------|---------|
| **Locked** | Mnemonic not in memory; push/pull will not export or import API keys |
| **Unlocked** | Mnemonic cached in the backend process and OS keyring |

- **Lock session** — clears the cached mnemonic from memory (does not remove it from the OS keyring). Safe when you step away.
- **Restart Suzent** — the mnemonic is auto-reloaded from the OS keyring on the next sync that needs it.

The mnemonic is **never** written to:

- `sync_profiles.json`
- Any plain-text file
- GitHub (only ciphertext and KDF metadata go to GitHub)

## Push and pull behaviour

| Operation | Locked / no mnemonic | Unlocked |
|-----------|----------------------|----------|
| **Push** | Requires mnemonic when encrypted sync is enabled | Exports keys from local secret manager → encrypts → commits `bundles.json` |
| **Pull** | Requires mnemonic when encrypted bundles exist | Restores config/skills/memory and decrypts bundles into the local keyring |
| **Auto-sync** | Skips secret import/export (warning logged) if mnemonic unavailable | Includes secrets automatically |

Config, skills, and memory sync do not require the mnemonic when the repo has no encrypted API key bundles. If bundles exist, Suzent prompts for the mnemonic before pull so secret import is always explicit.

## What is stored on GitHub

`bundles.json` (format_version 2) contains:

```json
{
  "format_version": 2,
  "kdf": {
    "algorithm": "scrypt",
    "salt": "<base64 random 32-byte salt>",
    "n": 131072,
    "r": 8,
    "p": 1
  },
  "mnemonic_version": 1,
  "mnemonic_fingerprint": "<first 8 hex chars of SHA-256(mnemonic)>",
  "devices": [
    { "device_id": "...", "device_name": "My Laptop", "mnemonic_version": 1 }
  ],
  "bundles": [
    {
      "provider": "openai",
      "key_name": "OPENAI_API_KEY",
      "ciphertext": "<base64 AES-256-GCM ciphertext>",
      "nonce": "<base64 12-byte nonce>",
      "key_version": 1
    }
  ]
}
```

- **Salt** and **KDF parameters** are public metadata; they prevent precomputed attacks.
- **`mnemonic_fingerprint`** lets Suzent detect rotation without revealing the phrase.
- **Ciphertext** is useless without the mnemonic.

## Cryptography (for contributors and security review)

Implementation: `src/suzent/sync/mnemonic.py` and `src/suzent/sync/secrets.py`.

| Step | Detail |
|------|--------|
| Phrase format | BIP39 — 12 words from a fixed 2048-word English wordlist |
| KDF | scrypt (N=2^17, r=8, p=1, random 32-byte salt per-file) |
| Symmetric cipher | AES-256-GCM (256-bit key, 96-bit nonce, authenticated) |
| Verification | Registration decrypts a sample bundle to verify the phrase before saving |
| Rotation | New salt + new key; `mnemonic_version` counter detects stale devices |

### Legacy format (format_version 1)

Earlier setups used a freeform passphrase with PBKDF2-SHA256 (600,000 iterations) and Fernet (AES-128-CBC + HMAC-SHA256). When Suzent encounters a format_version 1 bundle on push, it automatically migrates to format_version 2 by re-encrypting with the mnemonic. No manual action required.

## Security properties

**Provides:**

- GitHub or repo leaks expose encrypted blobs, not plaintext API keys
- No secret key file synced to the remote
- AES-256-GCM provides authenticated encryption (ciphertext tampering is detected)
- scrypt makes brute-force attacks expensive

**Does not provide:**

- Protection if someone has your mnemonic phrase
- Protection against malware on an unlocked machine (keys exist in memory and local keyring)
- Automatic multi-user access control on GitHub (repo access still matters)

**If you lose the mnemonic:**

- Ciphertext on GitHub cannot be decrypted
- Re-enter keys locally, generate a new mnemonic, and push new bundles. Old bundles remain in the repo but are orphaned — remove them by disabling and re-enabling encrypted sync.

## API (mnemonic-related)

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/sync/shibboleth/unlock` | POST | `profile_id`, `shibboleth` | Cache mnemonic for the session |
| `/sync/shibboleth/lock` | POST | `profile_id` | Clear session cache |
| `/sync/secrets/enable` | POST | `profile_id`, `mnemonic` | Enable flag + unlock |
| `/sync/secrets/disable` | POST | `profile_id` | Disable flag + lock |
| `/sync/secrets/unlock` | POST | `profile_id`, `mnemonic` | Verify mnemonic and register device |
| `/sync/secrets/rotate` | POST | `profile_id`, `mnemonic` | Rotate to new mnemonic |
| `/sync/secrets/register-device` | POST | `profile_id`, `mnemonic` | Register this device with existing mnemonic |
| `/sync/push` | POST | optional `shibboleth` | One-shot mnemonic without session unlock |
| `/sync/pull` | POST | optional `shibboleth` | One-shot mnemonic without session unlock |

## FAQ

### Is the mnemonic the same as my GitHub password?

No. GitHub authentication (Device Flow token) lets Suzent talk to GitHub. The mnemonic only encrypts API keys inside the sync payload — GitHub never sees it.

### Can I use GitHub Sync without a mnemonic?

Yes. Most users only sync config, skills, and memory. Add encrypted API sync only if you need API keys on multiple machines without re-entering them manually.

### Why did Pull ask for a mnemonic on a new device?

The repo contains encrypted API key bundles. Suzent can restore all other portable data without the mnemonic, but requires it before importing encrypted keys into the new device's local secret store.

### My API key is set from ENV. Will it sync?

No. Environment-only keys can be read at runtime, but they are not exported because Suzent does not own them in its secret store. Save the key through Suzent's provider settings, then push with the mnemonic unlocked.

### Is `sync_profiles.json` shared between devices?

No. `sync_profiles.json` contains local repo paths and device-local sync settings. It stays on each device and is excluded from the GitHub payload.

### Why "Shibboleth"?

A shared secret word members of a group know — here, the mnemonic phrase only people you trust should know. The name predates the switch to BIP39 word phrases and is kept for historical continuity.

### Does encrypted sync replace the OS keyring?

No. Keys still live in the system keyring locally. GitHub only receives encrypted exports for transport.

### What happened to the old passphrase format?

Earlier versions used a freeform passphrase (format_version 1, PBKDF2 + Fernet). Suzent migrates those bundles automatically to format_version 2 (BIP39 + scrypt + AES-256-GCM) on the next push. You will be prompted to generate or enter a mnemonic if you have existing format_version 1 bundles.

## See also

- [GitHub Sync](./README.md) — Quick start, push/pull, auto-sync
- [Providers](../providers/README.md) — where API keys are configured
