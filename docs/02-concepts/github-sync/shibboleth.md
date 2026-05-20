# Shibboleth (Passphrase)

**Shibboleth** is Suzent’s name for the passphrase you choose to encrypt API keys before they are stored in your GitHub sync repository. It is not your GitHub password, not your Suzent login, and not stored on disk by Suzent.

Use Shibboleth when you want provider API keys to follow your portable brain to another device **without** storing plaintext secrets on GitHub.

## When you need it

| Goal | Shibboleth required? |
|------|----------------------|
| Sync config, skills, markdown memory via GitHub | No |
| Sync API keys (OpenAI, Anthropic, etc.) via GitHub | Yes — enable **encrypted API sync** and use the same passphrase on every device |

Encrypted API sync is **off by default**. You opt in under Settings → Data → GitHub Sync → Advanced → **Shibboleth (Passphrase)**.

## How it works (overview)

```
Passphrase (you remember)
        │
        ▼
   PBKDF2-SHA256 (600,000 iterations + random salt)
        │
        ▼
   Fernet encryption key
        │
        ├──► Encrypt each API key from local keyring
        │         └──► ciphertext in bundles.json
        │
        └──► Push bundles.json to GitHub (inside suzent-sync/)
```

On another device, the same passphrase derives the same key and decrypts bundles into that machine’s local keyring.

Details of algorithms and file format are below.

## Setup (first device)

1. Complete [GitHub Sync Quick start](./README.md) so a profile and remote exist.
2. Open **Advanced options** → **Shibboleth (Passphrase)**.
3. Enter a passphrase (minimum **12 characters**) and confirm it.
4. Click **Set up Shibboleth** / **Enable encrypted API sync**.
5. Click **Unlock** (or enable flow unlocks for you).
6. **Push** to GitHub — API keys are exported as ciphertext in `suzent-sync/_sync/secrets/bundles.json`.

## Second device

1. Set up GitHub Sync with the same GitHub repo. Fresh devices clone the existing sync repo when the local sync folder is empty.
2. Open Shibboleth and **Unlock** with the **same passphrase** as the first device.
3. **Pull**. Config, skills, memory, and encrypted API key bundles are restored/imported.

If the passphrase is wrong, unlock and import fail with an incorrect passphrase error. Suzent cannot recover the keys without it.

## Unlock and lock (session)

| State | Meaning |
|-------|---------|
| **Locked** | Passphrase not in memory; push/pull will not export or import API keys when encrypted sync is enabled |
| **Unlocked** | Passphrase cached in the **running backend process** only |

- **Lock session** — Clears the cached passphrase. Safe when you step away from the machine.
- **Restart Suzent or the backend** — Always locked again; unlock required before the next secret sync.

The passphrase is **never** written to:

- Disk
- `sync_profiles.json`
- GitHub (only ciphertext and KDF metadata go to GitHub)

## Push and pull behavior

When `encrypted_secret_sync_enabled` is true on your profile:

| Operation | Locked | Unlocked |
|-----------|--------|----------|
| **Push** | Fails (unlock required) | Exports keys from local secret manager → encrypts → commits `bundles.json` |
| **Pull** | Requires unlock when encrypted bundles exist | Restores config/skills/memory and decrypts bundles into the local keyring |
| **Auto-sync** | Skips secret import/export (warning logged) | Includes secrets if unlocked |

Config, skills, and memory sync do not require Shibboleth when the repo has no encrypted API key bundles. If bundles exist, Suzent asks for Shibboleth before pull so secret import is explicit.

## What is stored on GitHub

`bundles.json` contains:

```json
{
  "format_version": 1,
  "kdf": {
    "algorithm": "pbkdf2-sha256",
    "iterations": 600000,
    "salt": "<base64-url-safe random salt>"
  },
  "bundles": [
    {
      "provider": "openai",
      "key_name": "OPENAI_API_KEY",
      "ciphertext": "<fernet token>",
      "nonce": "<metadata>",
      "key_version": 1
    }
  ]
}
```

- **Salt** and **iterations** are public metadata; they prevent precomputed attacks.
- **Ciphertext** is useless without the passphrase.
- Legacy **`sync_secret.key`** files are excluded from the sync payload and must not be committed.

## Cryptography (for contributors and security review)

Implementation: `src/suzent/sync/shibboleth.py` and `src/suzent/sync/secrets.py`.

| Step | Detail |
|------|--------|
| Passphrase validation | Minimum 12 characters |
| KDF | PBKDF2-HMAC-SHA256, 600,000 iterations, per-file salt |
| Symmetric cipher | Fernet (AES-128-CBC + HMAC-SHA256) |
| Verification | Unlock decrypts a sample bundle to verify passphrase |

Changing the passphrase on one device without re-pushing new bundles leaves other devices unable to decrypt old ciphertext until you push new bundles encrypted with a new passphrase (operational detail: treat passphrase changes like a rotation — re-enable and push from a trusted device).

## Security properties

**Provides:**

- GitHub or repo leaks expose encrypted blobs, not plaintext API keys
- No secret key file synced to the remote
- Passphrase strength is under your control

**Does not provide:**

- Protection if someone has your passphrase
- Protection against malware on an unlocked machine (keys exist in memory and local keyring)
- Automatic multi-user access control on GitHub (repo access still matters)

**If you forget the passphrase:**

- Ciphertext on GitHub cannot be decrypted
- Re-enter keys locally and push new bundles after setting a new passphrase (old bundles remain orphaned)

## API (Shibboleth-related)

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/sync/shibboleth/unlock` | POST | `profile_id`, `shibboleth` | Verify and cache passphrase |
| `/sync/shibboleth/lock` | POST | `profile_id` | Clear cache |
| `/sync/secrets/enable` | POST | `profile_id`, `shibboleth` | Enable flag + unlock |
| `/sync/secrets/disable` | POST | `profile_id` | Disable flag + lock |
| `/sync/push` | POST | optional `shibboleth` | One-shot passphrase without unlock |
| `/sync/pull` | POST | optional `shibboleth` | One-shot passphrase without unlock |

## FAQ

### Is Shibboleth the same as my GitHub password?

No. GitHub authentication (`gh` or PAT) lets Suzent talk to GitHub. Shibboleth only encrypts API keys inside the sync payload.

### Can I use GitHub Sync without Shibboleth?

Yes. Most users only sync config, skills, and memory. Add Shibboleth only if you need API keys on multiple machines without re-entering them manually.

### Why did Pull ask for Shibboleth on a new device?

The repo contains encrypted API key bundles. Suzent can still store normal portable data in GitHub, but it requires your passphrase before importing the encrypted keys into the new device's local secret store.

### My API key is set from ENV. Will Shibboleth sync it?

No. Environment-only keys can be read at runtime, but they are not exported because Suzent does not own them in its secret store. Save the key through Suzent's provider settings, then push with Shibboleth unlocked.

### Is `sync_profiles.json` shared between devices?

No. `sync_profiles.json` contains local repo paths and device-local sync settings. It stays on each device and is excluded from the GitHub payload.

### Why “Shibboleth”?

A shared secret word members of a group know — here, the passphrase only people you trust should know.

### Does encrypted sync replace the OS keyring?

No. Keys still live in the system keyring locally. GitHub only receives encrypted exports for transport.

## See also

- [GitHub Sync](./README.md) — Quick start, push/pull, auto-sync
- [Providers](../providers/README.md) — where API keys are configured
