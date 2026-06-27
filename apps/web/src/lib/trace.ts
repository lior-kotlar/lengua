/**
 * W3C Trace Context `traceparent` generation for the API client (task 5.5.1).
 *
 * The web app deliberately does NOT ship a full OpenTelemetry browser SDK — that would add a large
 * dependency to the bundle for what we need here, which is simply to *start* a trace on the client
 * and let it continue into the API. So we generate a minimal, spec-compliant `traceparent` header
 * per API request and inject it in the api-client request middleware (`@/lib/api-client`); the
 * FastAPI server then continues that trace, so its server span and the DB/LLM child spans all share
 * the trace id minted here (proven end-to-end by `apps/api/tests/obs/test_trace_continuation.py`).
 *
 * Format (W3C Trace Context, version `00`):
 *
 *     traceparent = "00" "-" trace-id "-" parent-id "-" trace-flags
 *
 * - `trace-id`    — 16 random bytes (32 lowercase hex), never all-zero.
 * - `parent-id`   — 8 random bytes (16 lowercase hex), never all-zero. This is the client span id;
 *                   the server parents its span under it.
 * - `trace-flags` — `01` (sampled) so the backend records the continued trace.
 *
 * See https://www.w3.org/TR/trace-context/#traceparent-header. Exporting a browser client span to
 * Tempo (a real web OTLP SDK) is a deferred Phase-6 enhancement; today the browser only *starts* the
 * trace via this header and the assembled trace lives server-side.
 */

/** The traceparent version byte we emit (this is a version-`00` generator). */
export const TRACEPARENT_VERSION = '00';

/** trace-flags: sampled. We always sample so the continued server trace is recorded. */
export const TRACEPARENT_FLAGS_SAMPLED = '01';

/**
 * Format validator for a version-`00` `traceparent`. Checks the shape only; the "not all-zero"
 * trace-id / parent-id semantic constraint is guaranteed by {@link generateTraceparent}. Exported so
 * tests (vitest unit + Playwright network assertion) assert against one canonical pattern.
 */
export const TRACEPARENT_REGEX = /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/;

/** Fill `byteLength` bytes with randomness. Injectable so tests are deterministic. */
export type RandomBytes = (byteLength: number) => Uint8Array;

/** Default cryptographic source — Web Crypto, available in browsers and Node ≥ 19 / jsdom. */
const cryptoRandomBytes: RandomBytes = (byteLength) =>
  crypto.getRandomValues(new Uint8Array(byteLength));

/** Lowercase hex of every byte (each padded to two chars). */
function toHex(bytes: Uint8Array): string {
  let hex = '';
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, '0');
  }
  return hex;
}

/**
 * A random lowercase-hex id of `byteLength` bytes, never all-zero.
 *
 * The W3C spec declares an all-zero trace-id / parent-id invalid; a cryptographic draw makes that
 * astronomically unlikely, but we regenerate on the off chance so an invalid id is never emitted.
 */
function randomHexId(byteLength: number, randomBytes: RandomBytes): string {
  let bytes = randomBytes(byteLength);
  while (bytes.every((byte) => byte === 0)) {
    bytes = randomBytes(byteLength);
  }
  return toHex(bytes);
}

/**
 * Generate a fresh W3C `traceparent` header value (version `00`, sampled).
 *
 * A new random trace-id + parent-id (the client span id) per call, so each API request starts its
 * own trace. `randomBytes` is injectable for deterministic tests; it defaults to Web Crypto.
 */
export function generateTraceparent(
  randomBytes: RandomBytes = cryptoRandomBytes,
): string {
  const traceId = randomHexId(16, randomBytes);
  const parentId = randomHexId(8, randomBytes);
  return `${TRACEPARENT_VERSION}-${traceId}-${parentId}-${TRACEPARENT_FLAGS_SAMPLED}`;
}
