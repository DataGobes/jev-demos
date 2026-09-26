/**
 * Composite scoring maths for the Cringe-o-Meter.
 *
 * Every dimension is already normalised to 0..1 by the server route (Score
 * answers divided by levels-1, Noul answers used as-is — see
 * src/lib/dimensions.ts and src/app/api/judge/route.ts). This module only
 * combines those cached 0..1 values with the viewer's slider weights, so
 * re-weighting never has to re-call the API.
 */

export interface DimensionWeights {
  [dimensionId: string]: number;
}

export interface DimensionValues {
  [dimensionId: string]: number;
}

/** Weight mass (in slider units) that counts as a post's "worst offences". */
const TOP_WEIGHT_MASS = 3;
/** Share of the composite driven by the worst offences vs. the overall mean. */
const TOP_SHARE = 0.8;

/**
 * Cringe doesn't average out: a post that maxes three dimensions is cringe
 * even if the other five are clean, and a plain weighted mean scored such
 * posts around 0.4. So the composite blends the weighted mean of the
 * worst-scoring TOP_WEIGHT_MASS of slider weight with the weighted mean over
 * everything. Falls back to 0 when every weight is zero.
 */
export function computeComposite(
  values: DimensionValues,
  weights: DimensionWeights,
): number {
  const entries = Object.keys(values)
    .map((id) => ({ value: values[id], weight: weights[id] ?? 0 }))
    .filter((entry) => entry.weight > 0)
    .sort((a, b) => b.value - a.value);

  let weightedSum = 0;
  let totalWeight = 0;
  let topSum = 0;
  let topWeight = 0;

  for (const { value, weight } of entries) {
    weightedSum += value * weight;
    totalWeight += weight;

    const take = Math.min(weight, TOP_WEIGHT_MASS - topWeight);
    topSum += value * take;
    topWeight += take;
  }

  if (totalWeight === 0) return 0;
  return TOP_SHARE * (topSum / topWeight) + (1 - TOP_SHARE) * (weightedSum / totalWeight);
}

/** Ranks dimensions by their weighted contribution, most cringe first. */
export function topContributors(
  values: DimensionValues,
  weights: DimensionWeights,
  count: number,
): string[] {
  return Object.keys(values)
    .map((id) => ({ id, contribution: values[id] * (weights[id] ?? 0) }))
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, count)
    .map((entry) => entry.id);
}

export interface Verdict {
  label: string;
  blurb: string;
}

// Tiers are denser in the 0.15–0.6 band, where most real posts land; the top
// tiers read as badges rather than insults so people want to share them.
const VERDICT_TIERS: { below: number; verdict: Verdict }[] = [
  {
    below: 0.12,
    verdict: {
      label: "Suspiciously human",
      blurb: "No hook, no lesson, no ask. The algorithm will never find this.",
    },
  },
  {
    below: 0.25,
    verdict: {
      label: "Actually fine",
      blurb: "You said a thing and then stopped. Rare. Post it.",
    },
  },
  {
    below: 0.4,
    verdict: {
      label: "Lightly optimised",
      blurb: "A faint whiff of personal brand. Your colleagues will still make eye contact.",
    },
  },
  {
    below: 0.55,
    verdict: {
      label: "Algorithm-curious",
      blurb: "You've read a thread about hooks, and it shows.",
    },
  },
  {
    below: 0.7,
    verdict: {
      label: "Thought leader in training",
      blurb: "The line breaks are doing a lot of work here. Agree?",
    },
  },
  {
    below: 0.85,
    verdict: {
      label: "Certified LinkedInfluencer",
      blurb: "Somewhere, a toddler just taught someone about B2B sales.",
    },
  },
];

const TOP_VERDICT: Verdict = {
  label: "Peak LinkedIn",
  blurb: "Humbled. Thrilled. Honored. The engagement will be incredible.",
};

/** Maps the composite 0..1 score from computeComposite() to a verdict tier. */
export function verdictFor(score: number): Verdict {
  return VERDICT_TIERS.find((tier) => score < tier.below)?.verdict ?? TOP_VERDICT;
}
