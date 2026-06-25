// THROWAWAY proof module (0.5.4) — reverted right after CI proves coverage<80% fails.
// Valid TS (so tsc --noEmit stays green) but never imported by any test, so vitest v8
// `all: true` counts it as uncovered and the 80% threshold fails.

export function proofClassify(n: number): string {
  if (n > 100) return 'huge';
  if (n > 10) return 'big';
  if (n > 0) return 'small';
  if (n === 0) return 'zero';
  return 'negative';
}

export function proofSum(items: number[]): number {
  let total = 0;
  for (const it of items) {
    if (it % 2 === 0) {
      total += it;
    } else {
      total -= it;
    }
  }
  return total;
}
