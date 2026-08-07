/**
 * NEXUS Member Product generation marker (V18.2.11 Product 2.0).
 * Automated QA must fail if this is not 2.
 */
export const MEMBER_PRODUCT_GENERATION = 2 as const;

export type MemberProductGeneration = typeof MEMBER_PRODUCT_GENERATION;

export function assertMemberProductGeneration(): void {
  if (MEMBER_PRODUCT_GENERATION !== 2) {
    throw new Error(
      `HARD FAIL: member_product_generation=${MEMBER_PRODUCT_GENERATION}; expected 2`,
    );
  }
}

assertMemberProductGeneration();
