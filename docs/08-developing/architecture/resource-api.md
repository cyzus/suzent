---
sidebar_position: 11
---

# Shared resource API

Desktop and paired native clients use a versioned resource interface at `/api/v1`.
Models, projects, chat navigation/details/actions, notifications, approvals, media,
uploads, live streams and voice share an operation registry. Desktop-only chat and
project controls also live in that registry with an explicit host-only policy.
Device pairing/bootstrap and system administration remain separate.

## Ownership

`src/suzent/api/operations.py` declares method, path, request/response types,
permissions, conversation scope and transport kind. `contracts.py` contains the
Pydantic boundary models. `access.py` resolves a local operator, a full-access host
credential or a paired-device grant; `router.py` enforces the declared policy before
calling `resources.py` or the existing domain handler. Desktop-only extensions
reuse their existing validators and preserve their configuration/history fields.

Resource handlers still own data visibility and conditional actions. A chat ID in
a list, navigation metadata, an approval decision or a streamed event must be
checked against the same grant. Successful static authorization does not make an
entire database response safe to return. Live device streams and voice recheck
revocation while active; attachment IDs remain bound to device and conversation.

The TLS and encrypted relay gateway allow common paths but replace the transport
identity, so a local connection cannot acquire operator access. A host token does
not turn into operator access through that gateway. Legacy mobile routes continue
to require a paired grant, including on loopback.

## Generated protocol

Run `uv run python scripts/generate_resource_api.py` after changing the registry or
models. It emits the OpenAPI document and Swift, Kotlin and TypeScript DTOs, JSON
clients and request/path descriptors. Run with `--check` to verify checked-in
outputs; backend CI runs this check. Generation requires no external service.
See [the contract guide](../../../packages/api-contract/README.md) for the extension
workflow and generated API names.

Adapters retain platform-specific transport behavior: TLS pinning, credential
headers, redirect rejection, file streaming and stream recovery. The native
presentation/domain models remain independent of generated wire types. Opaque
runtime tool payloads stay JSON values; permitted unknown response fields survive
native decoding. Resource identifiers are validated as one path segment and
encoded once at the platform URL boundary.

Desktop code uses generated paths when it supplies its existing richer host-owned
payloads, and typed SDK methods for common JSON requests. Native resource requests
use generated DTO encoders and request descriptors; no per-operation URL or JSON
encoder is duplicated in the native network clients.

## Version skew

`/mobile/client/session` advertises `resource_api: 1`. Native adapters select common
paths only after negotiating it. Otherwise their generated descriptors retain the
original paths. Writes are never retried on a different endpoint when the server
returns an error. Existing send-id deduplication and snapshot/cursor recovery are
unchanged.

Legacy mobile URLs are aliases built from the same operation registry. Legacy
desktop URLs remain supported for already installed frontends. Public resource
schema discovery requires authentication at `/api/v1/openapi.json`; available
operations can be queried at `/api/v1/capabilities`. A capability identifies an
available operation; resource scope and conditional permissions still apply.

## Model catalog reads

The backend caches public model IDs and favorites in memory for up to 60 seconds.
Provider configuration/default-model invalidation, favorite updates, discovery
writes and registry reloads invalidate it immediately. Manual file/environment
changes are bounded by the TTL. Credentials and device permissions are not cached;
authorization is checked per request and again after asynchronous catalog loading.
Cold catalog reads run off the event loop.

`GET /api/v1/chats/{chat_id}?include_models=false` (also supported by the legacy
alias) omits the catalog. Native foreground conversation polls use this query and
retain the list already loaded for the conversation. Opening a chat and loading
an empty composer retain the default behavior. Opening the model picker keeps its
current contents while revalidating the dedicated catalog. Network discovery runs
through explicit model refresh and the existing startup/configuration flows, not
through routine chat polling. Query DTOs and request builders are generated from
the operation's query model just like JSON request bodies.
