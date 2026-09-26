/**
 * Single source of truth for every cringe dimension the app judges.
 *
 * Both the server route (src/app/api/judge/route.ts) and the client UI
 * (src/components/Cringometer.tsx) import this file so the question wording,
 * the rubric, and the display copy can never drift apart.
 *
 * `primitive` selects which TypeSafe System One question type builds the
 * judgment:
 *  - "score": degree matters. `criteria` is an ORDERED tuple of levels
 *    (index 0..levels-1), each a concrete situation description. The raw
 *    answer's `score` is a probability-weighted mean across those levels;
 *    normalise by dividing by (levels - 1) to land in 0..1.
 *  - "noul": a yes/no presence check. The raw answer's `noul` is already a
 *    0..1 probability of "yes", so it needs no normalisation.
 */

export type Primitive = "score" | "noul";

export interface ScoreDimension {
  id: string;
  label: string;
  tagline: string;
  icon: IconId;
  primitive: "score";
  /** The Score question's instructions; `post` refers to the submitted draft. */
  instructions: string;
  /** Ordered level descriptions, index 0..levels-1. 4 levels here throughout. */
  criteria: readonly [string, string, string, string];
  /** Default slider weight (0..2 range in the UI). */
  defaultWeight: number;
}

export interface NoulDimension {
  id: string;
  label: string;
  tagline: string;
  icon: IconId;
  primitive: "noul";
  /** The Noul question's instructions; `post` refers to the submitted draft. */
  instructions: string;
  /** Optional descriptions of the yes/no outcomes, sent as the Noul criteria. */
  criteria?: { true: string; false: string };
  defaultWeight: number;
}

export type Dimension = ScoreDimension | NoulDimension;

export type IconId =
  | "brag"
  | "bait"
  | "trauma"
  | "buzzword"
  | "broetry"
  | "opener"
  | "lesson"
  | "hustle";

/** Number of ordered levels every Score dimension uses (index 0..3). */
export const SCORE_LEVELS = 4;

export const DIMENSIONS: Dimension[] = [
  {
    id: "humblebrag",
    label: "Humblebrag",
    tagline: "modesty as a delivery mechanism for a boast",
    icon: "brag",
    primitive: "score",
    defaultWeight: 1,
    instructions:
      "Rate how much the `post` disguises a boast as modesty or hardship — a " +
      "'humblebrag' where the writer downplays or complains about a personal " +
      "achievement while making sure everyone sees it.",
    criteria: [
      "The post states facts, opinions, or news without downplaying any personal achievement, or contains no self-referential achievement at all.",
      "The post mentions an accomplishment plainly and takes credit for it, without pretending to be modest or burdened by it.",
      "The post frames a personal win as a complaint, surprise, or confusion ('small brain over here got promoted, still don't know how') while clearly showcasing the achievement.",
      "The post goes out of its way to manufacture false modesty around a major achievement, using framing like 'I'm not usually one to share this but' or pairing the win with a fake hardship to earn sympathy and admiration at the same time.",
    ],
  },
  {
    id: "engagementBait",
    label: "Engagement bait",
    tagline: "'Agree?' 'Comment YES.' 'Tag a founder.'",
    icon: "bait",
    primitive: "score",
    defaultWeight: 1,
    instructions:
      "Rate how strongly the `post` uses engagement-bait tactics — explicit " +
      "prompts designed to farm likes, comments, or shares rather than share " +
      "genuine information, such as asking readers to type a word, react with " +
      "an emoji, tag someone, or answer a low-stakes yes/no question.",
    criteria: [
      "The post contains no call to engage; it states something and ends.",
      "The post ends with an open, genuine question inviting discussion of substance, such as asking what has worked for other people's teams.",
      "The post asks a low-effort rhetorical question clearly aimed at inflating engagement, like 'Agree?' or 'Am I wrong?', with an obvious expected answer.",
      "The post explicitly instructs readers how to react to farm the algorithm, e.g. 'Comment YES if you agree', 'Type 🔥 if this resonates', 'Repost if you know someone who needs this', or 'Tag a founder who needs to see this'.",
    ],
  },
  {
    id: "fakeVulnerability",
    label: "Fake vulnerability",
    tagline: "trauma, repackaged as a content hook",
    icon: "trauma",
    primitive: "score",
    defaultWeight: 1,
    instructions:
      "Rate how much the `post` packages personal hardship, trauma, or " +
      "vulnerability as content specifically engineered to earn sympathy, " +
      "engagement, or a business lesson, rather than an authentic, unadorned share.",
    criteria: [
      "The post contains no reference to personal hardship, struggle, or emotional vulnerability.",
      "The post mentions a real difficulty plainly, without dwelling on it for effect or converting it into a lesson.",
      "The post narrates a hardship with dramatic pacing or a cliffhanger, such as 'I didn't know if I'd make it', before pivoting to a takeaway, suggesting the story is being shaped for impact.",
      "The post explicitly monetizes trauma into content: a deeply personal crisis (illness, death, divorce, breakdown) is narrated in detail and then explicitly converted into a business or leadership lesson or call-to-action, with the suffering positioned mainly as a hook for the reveal.",
    ],
  },
  {
    id: "buzzwordDensity",
    label: "Buzzword density",
    tagline: "synergy, unlocked, double-clicked, disrupted",
    icon: "buzzword",
    primitive: "score",
    defaultWeight: 1,
    instructions:
      "Rate how saturated the `post` is with corporate or startup jargon and " +
      "buzzwords, such as 'synergy', 'circle back', 'move the needle', " +
      "'growth mindset', 'thought leader', 'disrupt', 'unlock value', " +
      "'double-click on', 'bandwidth', 'north star', 'level up', or 'game-changer'.",
    criteria: [
      "The post uses plain, concrete language throughout with no corporate jargon.",
      "The post contains one or two mild buzzwords but is otherwise written in plain language.",
      "The post leans heavily on buzzwords and jargon across multiple sentences, making it read like generic corporate-speak.",
      "Nearly every sentence of the post is built from buzzwords and jargon stacked together, to the point that concrete meaning is hard to extract.",
    ],
  },
  {
    id: "broetry",
    label: "Broetry",
    tagline: "one short line at a time",
    icon: "broetry",
    primitive: "noul",
    defaultWeight: 1,
    instructions:
      "Does the `post` use 'broetry' formatting — short, punchy statements each " +
      "broken onto their own line, stacked vertically like a poem, instead of " +
      "normal wrapping paragraphs?",
    criteria: {
      true: "Most of the post's sentences or clauses each sit on their own line, creating a vertical, poem-like stack of short lines.",
      false:
        "The post is written in normal prose paragraphs or sentences that wrap naturally, without a deliberate one-line-per-thought structure.",
    },
  },
  {
    id: "stockOpener",
    label: "“Humbled to announce”",
    tagline: "thrilled. honored. humbled. pick one.",
    icon: "opener",
    primitive: "noul",
    defaultWeight: 1,
    instructions:
      "Does the `post` open with, or prominently use, a stock announcement " +
      "phrase like 'I'm humbled to announce', 'I'm thrilled to share', " +
      "'I'm honored to announce', 'Excited to announce', or a close variant, " +
      "to introduce its news?",
    criteria: {
      true: "The post opens with, or prominently features, a stock phrase such as 'I'm humbled/thrilled/honored/excited to announce/share'.",
      false: "The post announces its news without using that stock phrasing.",
    },
  },
  {
    id: "mundaneLesson",
    label: "Toddler-industrial complex",
    tagline: "a leadership lesson from a juice box",
    icon: "lesson",
    primitive: "noul",
    defaultWeight: 1,
    instructions:
      "Does the `post` extract a business, leadership, or life lesson from a " +
      "mundane everyday moment (a coffee order, a traffic jam, a gym visit) " +
      "or from something a child or toddler said or did?",
    criteria: {
      true: "The post describes an ordinary, low-stakes moment or something a child or toddler did, then explicitly turns it into a business, leadership, or life lesson.",
      false: "The post does not turn a mundane moment or a child's action into a lesson.",
    },
  },
  {
    id: "hustleAdvice",
    label: "Unsolicited hustle advice",
    tagline: "5am. no days off. nobody's coming.",
    icon: "hustle",
    primitive: "noul",
    defaultWeight: 1,
    instructions:
      "Does the `post` hand out unsolicited hustle or grind advice — " +
      "prescriptive claims about waking up early, working harder than everyone " +
      "else, never taking a day off, or 'if you want it bad enough' style rules " +
      "framed as universal wisdom nobody asked for?",
    criteria: {
      true: "The post gives prescriptive hustle or grind advice, such as waking up at 5am, working weekends, or rules for 'those who really want it', presented as universal wisdom, unprompted.",
      false: "The post does not offer unsolicited hustle or grind style advice.",
    },
  },
];

export function getDimension(id: string): Dimension | undefined {
  return DIMENSIONS.find((d) => d.id === id);
}
