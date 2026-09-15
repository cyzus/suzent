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
