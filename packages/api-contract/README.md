# Shared resource API, version 1

Desktop, iOS and Android use `/api/v1` for common resources. The operation registry
in `src/suzent/api/operations.py` and Pydantic models in `contracts.py` are the
source of truth. `openapi.json` and the three generated client files are outputs.
The authenticated runtime schema is also available at `GET /api/v1/openapi.json`.

Generate and verify from the repository root:

```sh
uv run python scripts/generate_resource_api.py
uv run python scripts/generate_resource_api.py --check
```

CI rejects drift between the registry, schema and generated clients. Do not edit
generated files. No npm installation, network access or external generator is
required for generation after Python dependencies have been installed.

## Adding an operation

1. Define its Pydantic request and response models in `contracts.py`.
2. Implement its resource handler; reuse an existing domain service when present.
3. Register its method, path, models, permissions and conversation scope once in
   `operations.py`. Operations that expose host-owned settings must be host-only.
4. Regenerate, then use the emitted SDK method or request descriptor. A new
   phone-specific route or handwritten Swift/Kotlin request encoder is unnecessary.
5. Test authorization, visibility filtering, failed mutations and the wire shape.

The registry owns static permission checks. Conditional actions (for example
fork versus retry), filtering lists to authorized conversations, and stream-time
revocation checks remain in their resource handlers. Capability discovery lists
available operations, not a promise that every argument/action is authorized.

## Generated clients

- Swift: `ResourceClient`, `ResourceRequests`, and `Wire*` Codable/Sendable types.
- Kotlin: `ResourceClient`, `ResourceRequests`, and `Wire*` DTOs with JSON codecs.
- TypeScript: `ResourceClient`, `resourceRequests`, `resourcePaths`, and `Wire*` types.

Native network clients expose the complete generated API as `client.resourceAPI`.
New native features can use that surface directly without adding another method
to the handwritten domain/demo interface. Existing domain methods remain adapters
for the current UI. Desktop features can use `createResourceClient(getApiBase)`.

Transport is injected; generated clients never discover credentials, change
backends, or retry mutations. Native adapters retain their existing TLS pins,
redirect rejection, encrypted relay transport, upload streaming, opaque media IDs
and snapshot/cursor recovery. Domain presentation models are independent of wire
DTOs. Dynamic tool/agent payloads remain JSON values; models allowing additional
properties retain them in Swift/Kotlin `extraFields` (or `values` for opaque
objects). Response defaults and optional fields support version skew.

Request descriptors cover SSE, multipart, binary and WebSocket operations as well
as JSON. The platform adapter owns the actual streaming/file transport; these
operations are not sent through a JSON-only convenience method.

## Identity and compatibility

Local operator access and active full-access host credentials have host privileges.
Paired devices retain their approved conversation/action grants, even when their
request originates on loopback. Node and peer-agent credentials do not become
interactive-client credentials. The mobile TLS/relay gateway accepts common
resources but never grants host access, including to full-access host tokens.

Host-only operations and richer desktop request fields are explicitly declared.
The same resource URL can preserve the desktop's config/history payload while
rejecting it for a paired device. No arbitrary forwarding/proxy endpoint exists.

Old `/mobile/client/*` routes remain aliases of the same registry and handlers;
old desktop routes remain compatibility entry points to existing domain handlers.
The session advertises `resource_api: 1`. Native clients negotiate it before using
common paths, and use generated legacy paths when it is absent. They never replay
a failed write on another endpoint. Pairing/bootstrap and platform-specific system
settings keep their existing endpoints and credentials.
