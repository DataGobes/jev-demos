"""Synthetic support-message dataset for a fictional appliance shop.

Generates deterministic, seeded review/support text where keyword search on
"refund" and semantic refund *intent* deliberately diverge — the point of
the demo.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pyarrow as pa

if TYPE_CHECKING:
    import duckdb

ANCHOR_DATE = datetime(2026, 9, 1)  # noqa: DTZ001 -- naive, matches DuckDB TIMESTAMP (no tz)

INTENTS: tuple[str, ...] = (
    "refund_no_keyword",
    "keyword_no_refund",
    "refund_keyword",
    "churn_threat",
    "delivery_problem",
    "defect",
    "how_to",
    "praise",
    "neutral",
    "sarcasm",
)

_INTENT_WEIGHTS: tuple[float, ...] = (8, 4, 4, 10, 12, 14, 10, 20, 10, 8)

PRODUCTS: tuple[str, ...] = (
    "AeroBrew Coffee Machine",
    "AeroBrew Pro Coffee Machine",
    "EchoBrew Espresso Machine",
    "VelvetGrind Coffee Grinder",
    "CascadeClean Dishwasher",
    "CascadeClean Dishwasher XL",
    "BrightWash Dishwasher Compact",
    "TurboVac Cordless Vacuum",
    "TurboVac Pet Vacuum",
    "SilentSweep Robot Vacuum",
    "GlowBake Convection Oven",
    "GlowBake Smart Oven",
    "HearthGlow Toaster Oven",
    "SpinRight Washing Machine",
    "SpinRight Washing Machine Compact",
    "FreshCycle Washer Dryer Combo",
    "FrostPeak Refrigerator",
    "FrostPeak Mini Fridge",
    "NimbusChill Wine Cooler",
    "SteamPress Iron",
    "QuietHum Dryer",
    "CrispAir Fryer",
    "CrispAir Fryer XL",
    "PulseBlend Blender",
    "PulseBlend Blender Pro",
    "RapidBoil Kettle",
    "RapidBoil Kettle Steel",
    "PureMist Humidifier",
    "EverClean Water Filter Pitcher",
    "WarmWave Space Heater",
)

_OPENERS: tuple[str, ...] = (
    "",
    "",
    "Hi,",
    "Hello,",
    "Hey there,",
    "Hi team,",
    "So,",
    "Quick note —",
    "Update:",
    "Just a heads-up,",
    "To whom it may concern,",
)
_ANGRY_OPENERS: tuple[str, ...] = (
    "Ugh.",
    "Okay.",
    "Look.",
    "Seriously.",
    "Unbelievable.",
)

_CLOSERS: tuple[str, ...] = (
    "",
    "",
    "Thanks.",
    "Regards.",
    "Cheers.",
    "Thank you for your time.",
)
_ASK_CLOSERS: tuple[str, ...] = (
    "Thanks in advance.",
    "Please advise.",
    "Let me know.",
    "Appreciate it.",
    "Hope to hear back soon.",
)

_URGENCY_PHRASES: tuple[str, ...] = (
    "Please fix this ASAP.",
    "Need this resolved today.",
    "This is urgent.",
    "Before my trip next week.",
    "No rush, whenever you can.",
)

_TEMPLATES: dict[str, tuple[str, ...]] = {
    "refund_no_keyword": (
        "I want my money back for the {product}.",
        "Please send it back and credit my card — order {order}.",
        "This {product} doesn't work, I need my money returned.",
        "Cancel my order {order} and give me back what I paid.",
        "I'd like to return this {product} and get reimbursed in full.",
        "Just take it back and put the money on my card.",
        "Charge reversal please, the {product} is going back tomorrow.",
        "I'm sending the {product} back, please credit my account.",
        "Can you reverse the charge on order {order}?",
        "I want to return this and get a full reimbursement.",
        "Please put the money back on my card, the {product} is useless.",
        "I already boxed up the {product}, just need my money back now.",
        "Take it, I don't want it — money back please.",
        "Return label please, and reimburse me in full for order {order}.",
        "I'd rather have my cash back than another {product}.",
        "Money back.",
        "Want my money back.",
        "Send my money back, the {product} is going in the bin.",
    ),
    "keyword_no_refund": (
        "No need for a refund, the replacement {product} arrived and works great.",
        "Your refund policy is clear, thanks for explaining it.",
        "I was offered a refund but I'd rather keep the {product}.",
        "Already got my refund last week, no issues at all.",
        "Just checking your refund policy before I buy another {product}.",
        "The refund page on your site was easy to find, nice job.",
        "I didn't need to use the refund option after all, it just needed a reset.",
        "My colleague mentioned your refund process is painless, glad to hear it.",
        "Read the refund terms, all good, keeping the {product}.",
        "Thanks for the refund confirmation email, much appreciated.",
        "Refund came through fast, but I'm actually going to reorder the {product}.",
        "No refund necessary, support fixed it over chat.",
        "I know refund requests take a few days per your policy, that's fine, don't need one.",
        "Refund isn't needed, the {product} is working fine now.",
    ),
    "refund_keyword": (
        "I want a refund for order {order}.",
        "Please process a refund immediately.",
        "This is unacceptable, I demand a refund right now.",
        "Can I get a refund for this {product}?",
        "Requesting a full refund on {order}.",
        "I'd like a refund please.",
        "Refund me now, this {product} is garbage.",
        "How do I request a refund for order {order}?",
        "Give me a refund, I'm done waiting.",
        "Need a refund ASAP, the {product} never worked.",
        "Refund.",
        "Refund please.",
        "I'll take a refund on the {product}, not a replacement.",
    ),
    "churn_threat": (
        "If this isn't fixed I'm buying my next {product} from a competitor.",
        "This is the last {product} I ever buy from you.",
        "Switching brands after this, never ordering again.",
        "I'm done, going to order from someone else next time.",
        "One more issue like this and I'm taking my business elsewhere.",
        "Never again — there are better {product} options out there.",
        "You've lost a customer, I'll be shopping elsewhere from now on.",
        "This was my last order with you, ever.",
        "Not buying from this brand again.",
        "Taking my business to your competitor after this {product} experience.",
        "Done with this brand.",
        "My next {product} is coming from a different company.",
        "After {days} days of this, I'm shopping elsewhere for my next {product}.",
        "This {product} was my last purchase from this store.",
        "I've already ordered a replacement {product} from another brand.",
        "Telling everyone I know to skip this brand's {product} line.",
        "Order {order} was the final straw, my next {product} comes from someone else.",
        "{days} days of excuses about order {order}. I'm cancelling my account and moving on.",
        "I've been a customer for years, but after order {order} I'm closing my account.",
        "Your rival has the same {product} with actual support. Guess where order {order} should have gone.",
        "Consider order {order} my goodbye. {days} days without an answer is enough.",
        "I already told my family to avoid the {product}, and we're done ordering here after {order}.",
    ),
    "delivery_problem": (
        "My {product} still hasn't arrived, order {order} placed {days} days ago.",
        "Tracking says delivered but I never got the {product}.",
        "The courier left my order {order} at the wrong address.",
        "Package for order {order} has been stuck in transit for {days} days.",
        "Still waiting on my {product}, it's been {days} days.",
        "Delivery was supposed to be yesterday, no sign of the {product}.",
        "Box arrived empty, no {product} inside.",
        "Where is my order {order}?",
        "The {product} arrived damaged in shipping.",
        "Wrong item delivered, I ordered a {product}.",
        "Late again.",
        "Still no delivery update on {order}.",
        "Order {order} has been 'out for delivery' for {days} days.",
        "The {product} was left in the rain on my porch.",
        "Driver never rang the bell, marked order {order} as delivered anyway.",
        "My {product} shipment split into pieces, only half arrived.",
        "Order {order} shows delivered to a neighbor I don't know.",
    ),
    "defect": (
        "My {product} stopped working after {days} days.",
        "The {product} makes a loud grinding noise and won't turn on.",
        "There's a crack in the {product} straight out of the box.",
        "The display on my {product} is completely blank.",
        "The {product} leaks water everywhere.",
        "Button on the {product} is stuck, can't use it at all.",
        "The {product} overheats and shuts itself off.",
        "Motor died on the {product} after light use.",
        "The {product} arrived with a broken door hinge.",
        "It's broken.",
        "Doesn't turn on.",
        "The {product} smells like burning plastic when it runs.",
        "The {product} shuts down mid-cycle every single time.",
        "One of the buttons on the {product} fell off after {days} days.",
        "The {product} screen flickers and then goes dark.",
        "The {product} rattles violently when it's running.",
        "The seal on the {product} came loose after {days} days.",
        "My {product} won't hold a charge anymore.",
        "The {product} throws an error code every time I start it.",
        "The hinge on my {product} snapped after light use.",
    ),
    "how_to": (
        "How do I descale my {product}?",
        "What's the best cycle for towels on the {product}?",
        "Can the {product} be used with tap water?",
        "How often should I clean the filter on my {product}?",
        "Is there a child lock feature on the {product}?",
        "Where can I find the manual for the {product}?",
        "Does the {product} work with a voltage converter?",
        "How do I reset the {product} to factory settings?",
        "What detergent do you recommend for the {product}?",
        "Can I run the {product} overnight safely?",
        "How do I pair the {product} with the app?",
        "Any tips for the {product}?",
        "What's the warranty period on the {product}?",
        "Can two people control the {product} from the app at once?",
        "Is the {product} safe to leave running overnight?",
        "How much water does the {product} use per cycle?",
        "Can I order replacement parts for the {product}?",
        "Does the {product} have an eco mode?",
    ),
    "praise": (
        "Love my new {product}, works perfectly!",
        "Best {product} I've ever owned.",
        "The {product} exceeded my expectations, so easy to use.",
        "Fantastic quality on the {product}, worth every penny.",
        "My {product} arrived early and works beautifully.",
        "Five stars for the {product}, couldn't be happier.",
        "The {product} is quiet, fast, and reliable.",
        "Great job on the {product}, recommending it to everyone.",
        "Perfect.",
        "Amazing product, very happy.",
        "This {product} changed my morning routine for the better.",
        "Couldn't ask for a better {product}.",
        "Great {product}, doing exactly what I hoped.",
        "The {product} has been flawless for {days} days straight.",
        "Genuinely impressed with the {product}, recommend it to friends.",
        "The {product} feels sturdy and well built.",
        "My family loves the new {product}.",
        "The {product} was worth the wait, excellent build quality.",
        "Setup was a breeze and the {product} just works.",
        "The {product} looks great and performs even better.",
    ),
    "neutral": (
        "The {product} does what it says.",
        "It's fine, nothing special about the {product}.",
        "Received the {product} on time.",
        "The {product} looks as pictured.",
        "Setup took about {days} minutes for the {product}.",
        "Average {product}, does the job.",
        "The {product} matches the description.",
        "Ok.",
        "It works.",
        "The {product} was easy to unbox and set up.",
        "The {product} is what I expected, nothing more.",
        "The {product} runs about as loud as I expected.",
        "Packaging on the {product} was standard, nothing notable.",
        "The {product} has been sitting on the counter for {days} days now.",
        "Nothing to report on the {product} so far.",
        "The {product} is the same as my old one, basically.",
    ),
    "sarcasm": (
        "Great, another 'smart' {product} that can't tell time.",
        "Wow, {days} days for a {product} that broke on day one, impressive.",
        "Love how the {product} manual assumes I own a PhD.",
        "Sure, because a {product} that beeps at 3am is exactly what I wanted.",
        "Oh fantastic, the {product} app needs an update every single day.",
        "Nothing says 'premium' like a {product} held together with a sticker.",
        "Really thoughtful design, the {product} button is on the bottom, obviously.",
        "Terrific, my {product} 'self-cleans' by leaking on the floor.",
        "Cool, the {product} warranty card says 'good luck'.",
        "What a deal, paid full price for a {product} demo unit apparently.",
    ),
}

_TEMPLATE_WEIGHTS: dict[str, tuple[int, ...]] = {
    intent: tuple(4 if "{" in template else 1 for template in templates)
    for intent, templates in _TEMPLATES.items()
}

_DETAIL_TAILS: tuple[str, ...] = (
    "Ordered the {product}.",
    "This is about order {order}.",
    "Using it for {days} days now.",
    "Just my two cents on the {product}.",
    "For reference, order {order}.",
)

_NEGATIVE_ANGRY_INTENTS = frozenset(
    {
        "refund_no_keyword",
        "refund_keyword",
        "churn_threat",
        "delivery_problem",
        "defect",
    }
)
_URGENT_INTENTS = frozenset(
    {"delivery_problem", "defect", "refund_keyword", "refund_no_keyword"}
)

_STAR_DISTRIBUTIONS: dict[str, tuple[float, float, float, float, float]] = {
    "refund_no_keyword": (0.50, 0.30, 0.15, 0.04, 0.01),
    "keyword_no_refund": (0.05, 0.10, 0.15, 0.30, 0.40),
    "refund_keyword": (0.55, 0.30, 0.10, 0.04, 0.01),
    "churn_threat": (0.50, 0.35, 0.10, 0.04, 0.01),
    "delivery_problem": (0.30, 0.35, 0.20, 0.10, 0.05),
    "defect": (0.35, 0.30, 0.20, 0.10, 0.05),
    "how_to": (0.05, 0.10, 0.30, 0.35, 0.20),
    "praise": (0.02, 0.03, 0.05, 0.30, 0.60),
    "neutral": (0.05, 0.15, 0.50, 0.20, 0.10),
    "sarcasm": (0.40, 0.35, 0.15, 0.07, 0.03),
}


def _fill(template: str, rng: random.Random, product: str) -> str:
    return template.format(
        product=product,
        order=f"#{rng.randint(10_000, 99_999)}",
        days=rng.randint(1, 30),
    )


def _apply_anger(rng: random.Random, text: str, level: int) -> str:
    if level <= 0:
        return text
    text = text.rstrip(".!")
    if level == 1:
        return f"{text}!"
    words = text.split()
    if level == 2:
        if words:
            idx = rng.randrange(len(words))
            words[idx] = words[idx].upper()
        return " ".join(words) + "!!"
    return text.upper() + "!!!"


def _compose(
    rng: random.Random, core: str, product: str, *, urgency: bool, negative: bool
) -> str:
    parts: list[str] = []
    if rng.random() < 0.8:
        opener = rng.choice(_OPENERS + _ANGRY_OPENERS if negative else _OPENERS)
        if opener:
            parts.append(opener)
    parts.append(core)
    if urgency and rng.random() < 0.3:
        parts.append(rng.choice(_URGENCY_PHRASES))
    elif rng.random() < 0.2:
        parts.append(_fill(rng.choice(_DETAIL_TAILS), rng, product))
    if rng.random() < 0.7:
        closer = rng.choice(_CLOSERS + _ASK_CLOSERS if urgency else _CLOSERS)
        if closer:
            parts.append(closer)
    return " ".join(parts)


def _make_body(rng: random.Random, intent: str, product: str) -> str:
    templates = _TEMPLATES[intent]
    weights = _TEMPLATE_WEIGHTS[intent]
    template = rng.choices(templates, weights=weights, k=1)[0]
    core = _fill(template, rng, product)
    negative = intent in _NEGATIVE_ANGRY_INTENTS
    if negative:
        level = rng.choices([0, 1, 2, 3], weights=[40, 30, 20, 10])[0]
        core = _apply_anger(rng, core, level)
    ask = intent in _URGENT_INTENTS or intent == "how_to"
    return _compose(rng, core, product, urgency=ask, negative=negative)


def _pick_stars(rng: random.Random, intent: str) -> int:
    if rng.random() < 0.12:
        return rng.randint(1, 5)
    return rng.choices([1, 2, 3, 4, 5], weights=_STAR_DISTRIBUTIONS[intent], k=1)[0]


_SECONDS_PER_YEAR = 365 * 24 * 3600


# Churn threats cluster on a few troubled products so per-product rollups show real hotspots.
_CHURN_HOTSPOTS: tuple[tuple[str, float], ...] = (
    ("GlowBake Smart Oven", 0.30),
    ("SilentSweep Robot Vacuum", 0.16),
    ("FreshCycle Washer Dryer Combo", 0.09),
)


def _pick_product(rng: random.Random, intent: str) -> str:
    if intent == "churn_threat":
        roll = rng.random()
        for product, share in _CHURN_HOTSPOTS:
            if roll < share:
                return product
            roll -= share
    return rng.choice(PRODUCTS)


def generate_labeled(n: int, seed: int = 7) -> list[tuple[dict, str]]:
    """Generate `n` deterministic (row, intent_label) pairs for evaluation.

    The intent label never appears in the row itself.
    """
    rng = random.Random(seed)
    rows: list[tuple[dict, str]] = []
    for i in range(1, n + 1):
        intent = rng.choices(INTENTS, weights=_INTENT_WEIGHTS, k=1)[0]
        product = _pick_product(rng, intent)
        stars = _pick_stars(rng, intent)
        body: str | None = _make_body(rng, intent, product)
        if rng.random() < 0.03:
            body = "" if rng.random() < 0.5 else None
        created_at = ANCHOR_DATE - timedelta(seconds=rng.randint(0, _SECONDS_PER_YEAR))
        row = {
            "id": i,
            "product": product,
            "stars": stars,
            "body": body,
            "created_at": created_at,
        }
        rows.append((row, intent))
    return rows


def generate_reviews(n: int, seed: int = 7) -> list[dict]:
    """Generate `n` deterministic synthetic review/support-message rows."""
    return [row for row, _ in generate_labeled(n, seed)]


def load_reviews(
    con: duckdb.DuckDBPyConnection, n: int = 10_000, seed: int = 7
) -> None:
    """Create (or replace) the `reviews` table in `con` with synthetic data."""
    rows = generate_reviews(n, seed)
    table = pa.table(
        {
            "id": pa.array([r["id"] for r in rows], type=pa.int32()),
            "product": pa.array([r["product"] for r in rows], type=pa.string()),
            "stars": pa.array([r["stars"] for r in rows], type=pa.int32()),
            "body": pa.array([r["body"] for r in rows], type=pa.string()),
            "created_at": pa.array(
                [r["created_at"] for r in rows], type=pa.timestamp("us")
            ),
        }
    )
    con.register("_semsql_reviews_staging", table)
    try:
        con.execute(
            "CREATE OR REPLACE TABLE reviews AS SELECT * FROM _semsql_reviews_staging"
        )
    finally:
        con.unregister("_semsql_reviews_staging")
