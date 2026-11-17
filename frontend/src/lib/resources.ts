import { ResourceClient } from './resourceAPI.generated';

/** Keeps backend selection dynamic; the transport never retries a mutation. */
export function createResourceClient(getBase: () => string): ResourceClient {
  return new ResourceClient((request) =>
    fetch(`${getBase()}${request.path}`, {
      method: request.method,
      headers: request.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: request.body === undefined ? undefined : JSON.stringify(request.body),
    })
  );
}
