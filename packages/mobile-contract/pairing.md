# Mobile client pairing protocol 1

Mobile client grants are independent of host, agent and Node credentials. A
client grant cannot access the general backend API. Tool decisions require an explicit `approve_tools` grant.

## Bootstrap

The desktop chooses the exact `ClientPermissions` before generating a QR code.
The desktop defaults new invitations to **Full access**: all chats, creation, send, stop and tool approvals. “Restrict access” exposes individual scopes. Server model defaults remain false, and existing grants are not expanded.

1. The operator calls `POST /mobile/pairing/invite` with `{"permissions": {...}}`.
   The server freezes that scope and the desktop name in an in-memory invitation.
   The returned payload has `approval: "phone"`, a random 128-bit `pairing_id`,
   invitation secret and expiry. The desktop encodes these with `type:
   "suzent.mobile"`, `pairing_protocol: 1`, `origin` and optional `origins`.
2. Up to six unique origins are allowed, without paths, queries, fragments or
   user information. The QR is limited to 4096 UTF-8 bytes. Desktop includes
   discovered LAN, Tailscale IPv4 and MagicDNS addresses. Release clients retain
   only HTTPS candidates; Debug clients also permit HTTP.
3. The phone checks candidates with a three-second budget per request. It calls
   `GET /mobile/capabilities`, then `POST /mobile/pairing/preview` with only the
   random `pairing_id`. Neither request sends an invitation secret, durable
   credential or Authorization header. Preview is read-only and returns the
   matching invitation's desktop name, immutable permissions and expiry. This
   also prevents selecting a different Suzent server at a reused LAN address.
4. The phone displays that server-provided name, scope and selected origin. Only
   after **Confirm connection** does it call `POST /mobile/pairing/claim` with
   `pairing_id`, `invitation`, `display_name`, `platform` and the strict boolean
   `confirm_permissions: true`. Permission overrides are rejected. Missing
   confirmation cannot consume a preauthorized invitation.
5. The claim atomically consumes the invitation secret and returns a private
   `pickup_secret`. The phone immediately calls `POST /mobile/pairing/collect`.
   The server persists the new grant before returning its token, exactly once.
   There is no second desktop approval. The phone saves the credential in secure
   storage before activating its session. Claims and pickup are never retried
   automatically against another candidate address.
6. The new device appears in the desktop list and can be revoked there.

The preview endpoint is keyed by an unguessable invitation ID, not a user ID or
sequential code. It reveals no invitation/pickup secret and cannot issue a grant.
Invitations expire after five minutes; restarting the backend invalidates them.
The operator-only `POST /mobile/pairing/{pairing_id}/cancel` invalidates either an
unclaimed invitation or a claim whose credential has not yet been delivered.
Closing/cancelling the QR explicitly waits for cancellation; navigating away or
closing the desktop sends a best-effort keepalive cancellation. If the process or
network dies before delivery, expiry is the fallback. Cancellation after successful
credential delivery does not revoke that device; use the device's revoke action.

### Compatibility

An invitation created without permissions retains the original desktop-approval
flow. Its QR omits `approval`; after claim, it waits for the operator to compare
codes and call `/decide`. Updated phones omit `confirm_permissions` for that flow,
so old backends remain compatible. Older phones cannot claim new preauthorized
invitations and must update. The desktop UI checks the returned `approval` marker
before displaying a new-style QR.

The saved connection contains only the confirmed origin. Candidate selection is
for initial pairing, not automatic credential migration between networks.

## Access

Use a Bearer token on `/mobile/client/session`, `/mobile/client/chats`,
`/mobile/client/chats/{chat_id}`, `/mobile/client/send`, `/mobile/client/stop`,
and `/mobile/client/live`. No Node or host tokens are accepted here, even on
loopback. Session returns the device grant and supported protocol versions.

`permissions` contains `chat_ids`, `all_chats`, `create_chats`, `send`, `stop`, and `approve_tools` (missing means false).
Read access is limited to listed conversations unless `all_chats` is true.
`all_chats` includes future conversations. Newly created conversations are added
to the creating grant. Send and stop require both resource access and the
corresponding permission. Create accepts only title; send only chat_id and
message; stop only chat_id. Extra configuration, approval-resume payloads and
file paths are rejected. Desktop slash commands are not accepted by this client
surface. Existing conversation tool policy still applies.

`GET /mobile/client/chats/{chat_id}/approvals` returns the same pending native and ACP tool requests as desktop, limited to readable chats. `POST /mobile/client/approvals` requires `approve_tools` and accepts `{chat_id, decisions: [{chat_id, request_id, kind, action_id}]}`. The batch must match all current pending requests. Only offered once-only allow/deny actions are exposed. The server reconstructs native resumes from stored tool IDs and decisions; ACP resolves through the existing broker. Stale or duplicate decisions return 409. No client-provided arguments, remembered policy or global rules are accepted. Phones poll while foregrounded to reflect decisions on either device; POSTs are not retried automatically.

Live uses the same snapshot/cursor protocol 1 as desktop, with wait_ms capped at
1000. Revocation is checked before returning stream chunks and every 250 ms
while idle. Revocation closes the observer without cancelling the backend run.
The next request receives 401. Device management remains host-authorized:
`GET /mobile/devices` and `POST /mobile/devices/{device_id}/revoke`.

Durable tokens are high-entropy random values. Only SHA-256 hashes are stored in
an atomically replaced, owner-readable/writable file. A failed disk write does
not issue an in-memory grant. Pending bootstrap secrets are memory-only and
pending/list responses never expose them.

## Re-pairing an existing phone

Backends advertise `pairing_repair: 1`. Claim optionally accepts `repair_proof`
and `rotate`. The proof is HMAC-SHA256 keyed by the SHA-256 bytes of the saved
mobile token over `suzent-mobile-repair-v1:phone:<pairing_id>:<invitation>`.
The backend matches an active, finalized grant of the same platform and returns
`server_proof` using the `desktop` domain instead of `phone`. Clients verify this
before accepting `reused: true`; neither the token nor its stored hash is sent
in the unauthenticated claim. Unknown proofs receive an ordinary new grant.

An unchanged scope can reuse the existing token: collect returns `reused: true`
and its device, without a token. Changed scope, or `rotate: true`, returns a new
token with the same device ID. Clients force rotation when the selected origin
changes (for example LAN to Tailscale), never reusing the old bearer at a new
address. The replacement is provisional for five minutes. After securely saving
it alongside the previous token and origin for recovery, the phone posts to
`/mobile/client/pairing/confirm` authenticated with the new token. This atomically
retires all predecessors and finalizes the replacement. Confirmation is
idempotent. On an expired replacement, the client restores its previous saved
origin/token. A dropped confirmation response can be retried after restarting.
Device revocation removes both finalized and provisional tokens.

Use Settings → Pair again to retain the ownership proof. Forgetting the
connection, clearing app storage, or losing credentials prevents proof of the
old installation; it is treated as a new device. Existing duplicate grants are
not automatically removed by matching names or IP addresses.

## Local TLS invitations (QR protocol 2)

`POST /mobile/pairing/invite` accepts `local_tls: true`. It starts a dedicated
HTTPS listener, and returns its `origins` plus a `tls` object:

```json
{"version": 1, "ca_certificate": "base64-DER-device-CA", "fingerprint": "sha256-hex-of-DER"}
```

The desktop emits `pairing_protocol: 2` for these invitations. Protocol 2 requires
this object and exclusively HTTPS candidates, even in debug builds. Older phones
reject the new QR protocol rather than silently falling back to HTTP. Existing
public-CA HTTPS invitations remain protocol 1; `/mobile/capabilities` preserves
its protocol-1 bootstrap API and advertises `local_tls: 1`.

The QR is the out-of-band trust source, so it must be scanned from the intended
trusted desktop. Its hash detects mismatched certificate data, not a maliciously
replaced whole QR code. A phone validates the server chain against only that
device CA, including hostname/IP SAN, validity and server-auth usage. There is no
trust-all callback, global trust-store installation, or system-CA fallback for
pinned connections. Trust is saved alongside credentials and previous trust is
preserved during pending credential rotation. Normal public HTTPS sessions keep
the system trust store. The same client transport secures HTTP, SSE and Node WSS;
redirects remain disabled.

The backend stores its persistent CA key and certificate in
`USER_CONFIG_DIR/mobile_tls/identity.pem`, with owner-only permissions on POSIX.
Short-lived leaf certificates are renewed daily and when addresses change,
without changing the saved device CA. The listener's selected port is persisted
and reused across restarts. Do not delete this directory during upgrades. Loss or
replacement of the CA requires explicit re-pairing; a broken identity is never
silently regenerated. The CA has a 20-year validity period; replacing an expired
CA also requires re-pairing.

The TLS listener opens on first local pairing and resumes on later backend
starts. It exposes only mobile bootstrap/client routes and `/ws/node`, never the
operator endpoints. Proxy headers are ignored and all requests are treated as
remote, including connections from localhost. An occupied saved port is an error,
not a reason to advertise an arbitrary new port or downgrade transport.

Phones retain candidate origins and probe them without credentials before
reconnecting. The desktop also offers its `.local` hostname; this depends on the
host OS and network providing mDNS resolution. If all saved addresses change and
mDNS is unavailable, scan again. A recognized device can rotate its credential
without duplicating its device entry. No cross-network reachability is implied.

`tls-fixture.json` contains public test certificates only (no private keys). Its
short-lived leaf is tested at the fixed verification date 2030-01-01 so validity
checks remain deterministic.
