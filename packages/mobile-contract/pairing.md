# Mobile client pairing protocol 1

Mobile client grants are independent of host, agent and Node credentials. A
client grant cannot access the general backend API or approve agent tools.

## Bootstrap

1. The desktop operator creates an invitation with `POST /mobile/pairing/invite`.
2. The desktop encodes JSON in a QR code:
   `{"type":"suzent.mobile","pairing_protocol":1,"origin":"https://host:port","pairing_id":"…","invitation":"…","expires_at":1234567890}`.
   The origin contains no path, query, fragment or user information. This is an
   invitation secret, never a durable credential. Do not log or persist it.
3. The phone validates the payload and displays the destination before connecting.
   Release clients require HTTPS. Debug clients may explicitly use HTTP.
4. The phone checks `GET /mobile/capabilities`. Pairing and client protocol must
   equal 1, and `stream_protocols` must contain 1. No downgrade to host access.
5. The phone claims using `POST /mobile/pairing/claim` with `pairing_id`,
   `invitation`, `display_name` and `platform` (`ios` or `android`). Only one
   claimant succeeds. The response contains a private `pickup_secret`.
6. The phone displays the first six characters of `pairing_id`; the operator
   compares them and the device name in `GET /mobile/pairing/pending`, then
   submits `POST /mobile/pairing/{pairing_id}/decide` with `permissions` or null
   to deny. All permissions default to false and no conversations are shared.
7. The phone polls `POST /mobile/pairing/collect` using `pairing_id` and
   `pickup_secret`. Pending and denied responses contain only status. Approval
   returns `token` and `device`, exactly once. The phone saves the token in
   platform secure storage before opening its session.

Invitations expire after five minutes, including approval and pickup. Restarting
the backend invalidates pending invitations. Failed one-time delivery requires a
new invitation; it never falls back to a full-access credential. The device list
lets the operator revoke a grant left behind by an interrupted pickup.

## Access

Use a Bearer token on `/mobile/client/session`, `/mobile/client/chats`,
`/mobile/client/chats/{chat_id}`, `/mobile/client/send`, `/mobile/client/stop`,
and `/mobile/client/live`. No Node or host tokens are accepted here, even on
loopback. Session returns the device grant and supported protocol versions.

`permissions` contains `chat_ids`, `all_chats`, `create_chats`, `send`, and `stop`.
Read access is limited to listed conversations unless `all_chats` is true.
`all_chats` includes future conversations. Newly created conversations are added
to the creating grant. Send and stop require both resource access and the
corresponding permission. Create accepts only title; send only chat_id and
message; stop only chat_id. Extra configuration, approval-resume payloads and
file paths are rejected. Desktop slash commands are not accepted by this client
surface. Existing conversation tool policy still applies; approvals happen on
the desktop.

Live uses the same snapshot/cursor protocol 1 as desktop, with wait_ms capped at
1000. Revocation is checked before returning stream chunks and every 250 ms
while idle. Revocation closes the observer without cancelling the backend run.
The next request receives 401. Device management remains host-authorized:
`GET /mobile/devices` and `POST /mobile/devices/{device_id}/revoke`.

Durable tokens are high-entropy random values. Only SHA-256 hashes are stored in
an atomically replaced, owner-readable/writable file. A failed disk write does
not issue an in-memory grant. Pending bootstrap secrets are memory-only and
pending/list responses never expose them.
