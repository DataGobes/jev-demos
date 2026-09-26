/**
 * Original parody LinkedIn posts for the "try an example" buttons. Written
 * for this demo — not copied or adapted from any real post.
 */
export interface ExamplePost {
  id: string;
  label: string;
  post: string;
}

export const EXAMPLE_POSTS: ExamplePost[] = [
  {
    id: "promotion",
    label: "The humbled promotion",
    post: `I'm humbled to announce that I've been promoted to Senior VP of Synergy at Globex Corp.

Honestly? I didn't see this coming. I'm just a small-town kid who loves spreadsheets, and I still don't know how they picked me.

To everyone who doubted me: this one's for you. 🏆

Agree?`,
  },
  {
    id: "grindset",
    label: "The 4:45am grindset",
    post: `Woke up at 4:45am.
No snooze.
No excuses.

While you were sleeping,
I was already on my third cold plunge.

Success isn't given.
It's earned.

Sleep is for people who don't want it bad enough.

Comment YES if you're ready to grind.`,
  },
  {
    id: "juicebox",
    label: "The juice-box epiphany",
    post: `My 4-year-old spilled his juice box all over my laptop 10 minutes before a board call.

I wanted to scream. Instead I took a breath, and I realized: leadership isn't about control, it's about how you respond when the juice hits the fan.

That single moment taught me more about resilience than my entire MBA.

What's a small moment that changed how you lead?`,
  },
  {
    id: "doubleclick",
    label: "The buzzword ecosystem",
    post: `Let's double-click on this: most teams aren't failing because of bandwidth, they're failing because nobody wants to circle back and unlock real value.

We need to move the needle, level up our synergy, and become a true thought-leadership ecosystem.

If this resonates, type 🔥 in the comments. Repost if you know a founder who needs to see this.`,
  },
  {
    id: "thisPost",
    label: "This very post",
    post: `I'm humbled to announce that I built an AI that judges LinkedIn posts.

I didn't plan this.

I just showed up. Every evening. After bedtime.

Last week my toddler refused to eat broccoli.

And it hit me.

This wasn't about the broccoli. It was about the framing.

That's when I knew what this platform was missing: a Cringe-o-Meter.

8 questions. 1 API call. ~250 ms. Zero text generated.

It scores your post while you type. Humblebrag. Engagement bait. Broetry. And 5 more.

This post scores 90/100. Verdict: Peak LinkedIn.

I have never been prouder.

Agree? Comment CRINGE and I'll run your latest post through it 👇

P.S. The sincere bit: it runs on Jev, TypeSafe's System One model. It doesn't generate text, it returns typed judgments with calibrated probabilities. The sliders in the video re-weight the score without a single new API call, because the judgments are data and the scoring is just code.`,
  },
];
