/**
 * One-shot word handoff from Discover → Generate (group 4.7.2).
 *
 * Discover's "accept" feeds the suggested words into the EXISTING Generate flow (group 4.5) rather
 * than duplicating the generate → review → save UI: it stashes the accepted words here and navigates
 * to `/generate`, where the Generate workspace consumes them once on mount and prefills its word
 * input.
 *
 * Why a tiny module-level store instead of router navigation state: the handoff must be **one-shot**.
 * The Generate workspace is re-mounted per active language (`key={languageId}`), so a value read
 * from `location.state` would re-prefill on every language switch (and on reload). Consuming-and-
 * clearing here gives exactly-once semantics — a later remount, a language switch, or a manual visit
 * to `/generate` starts blank — without an effect or a history rewrite. The store holds only an
 * in-memory word list (no tokens, nothing persisted).
 */

/** Words awaiting pickup by the Generate workspace, or `null` when there are none. */
let pendingWords: string[] | null = null;

/**
 * Stash `words` for the Generate workspace to pick up on its next mount. An empty list clears any
 * pending handoff (there is nothing to hand off). The list is copied so later mutation of the
 * caller's array can't change what Generate receives.
 */
export function handOffWords(words: string[]): void {
  pendingWords = words.length > 0 ? [...words] : null;
}

/**
 * Consume any stashed words exactly once: returns them (and clears the store), or `null` when none
 * are pending. Calling twice in a row returns the words then `null`.
 */
export function takeHandedOffWords(): string[] | null {
  const words = pendingWords;
  pendingWords = null;
  return words;
}
