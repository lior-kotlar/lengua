/**
 * Hidden Sentry debug-error button (task 5.4.2).
 *
 * Renders NOTHING unless the build-time debug-tools flag is set ({@link debugToolsEnabled}, gated on
 * `VITE_ENABLE_DEBUG_TOOLS`) — a production build never sets it, so this can never appear or be
 * triggered in a deployed app. When enabled it renders a visually-hidden (`sr-only`) button that, on
 * click, throws a test error routed through the Sentry capture seam ({@link triggerDebugError}) — the
 * deliberate failure that proves the error-tracking path end-to-end.
 *
 * It is mounted app-globally (outside the route tree, like the consent banner) so the E2E can reach
 * it without authenticating. `onTrigger` is injectable so the click wiring is unit-testable without
 * actually throwing.
 */
import { debugToolsEnabled, triggerDebugError } from '@/lib/error-tracking';

export function DebugErrorButton({
  onTrigger = triggerDebugError,
}: {
  onTrigger?: () => void;
} = {}) {
  if (!debugToolsEnabled()) {
    return null;
  }
  return (
    <button
      type="button"
      data-testid="debug-throw-error"
      aria-label="Trigger a debug error"
      className="sr-only"
      onClick={() => onTrigger()}
    >
      Trigger debug error
    </button>
  );
}
