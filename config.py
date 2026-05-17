"""Tuneable knobs for the deck auditor.

Anything you'd ever want to tweak without touching logic lives here.
"""

# ---- Model / pricing ----
# Latest Sonnet at time of writing.
MODEL = "claude-sonnet-4-6"

# Per-million-token pricing in USD. Update as Anthropic pricing changes.
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

# Rough token estimation: 1 token ~ 0.75 words.
WORDS_PER_TOKEN = 0.75
# Prompt overhead (system + instructions) per slide we send to the API.
PROMPT_OVERHEAD_TOKENS_PER_SLIDE = 500
# Expected output tokens per slide (rewrites, judgments).
OUTPUT_TOKENS_PER_SLIDE = 300

# ---- Cost guardrails ----
DEFAULT_MAX_COST = 3.0       # warn + prompt above this
DEFAULT_HARD_CAP = 10.0      # refuse above this without --force

# ---- Deck size guardrails ----
SLIDE_WARN = 100
SLIDE_HARD_STOP = 250

# ---- Meeting + density ----
DEFAULT_MEETING_MINUTES = 30
MINUTES_PER_SLIDE = 2
MAX_WORDS_PER_SLIDE = 75
MAX_BULLETS_PER_SLIDE = 5

# ---- Scoring bands ----
BANDS = [
    (90, "ready"),
    (70, "close"),
    (50, "needs work"),
    (0,  "rebuild"),
]

# ============================================================
# AI voice word lists. Match as whole words, case-insensitive.
# ============================================================

CATEGORY_A_HYPE_VERBS = [
    "delve", "dive", "embark", "leverage", "utilize", "harness", "unlock",
    "unleash", "unravel", "empower", "transform", "revolutionize", "navigate",
    "foster", "cultivate", "amplify", "synthesize", "illuminate", "manifest",
    "galvanize", "permeate", "resonate", "underscore", "immerse", "elucidate",
    "substantiate", "encompass", "pioneer", "transcend", "optimize",
    "facilitate", "streamline", "spearhead", "championed", "showcase",
    "exemplify", "epitomize",
]

CATEGORY_B_HOLLOW_ADJECTIVES = [
    "robust", "seamless", "seamlessly", "holistic", "comprehensive",
    "cutting-edge", "innovative", "dynamic", "scalable", "transformative",
    "groundbreaking", "unprecedented", "remarkable", "compelling",
    "captivating", "riveting", "nuanced", "profound", "impactful", "pivotal",
    "paramount", "crucial", "bespoke", "esteemed", "meticulous", "vibrant",
    "intricate",
]

CATEGORY_C_METAPHOR_CRUTCHES = [
    "tapestry", "landscape", "journey", "beacon", "treasure trove",
    "labyrinth", "bastion", "realm", "zeitgeist", "fabric", "mosaic",
    "spectrum", "ecosystem", "arena", "frontier", "paradigm", "crossroads",
    "intersection", "unsung hero",
]

CATEGORY_G_STUFFY_CONNECTIVES = [
    "furthermore", "moreover", "additionally", "consequently", "subsequently",
    "nevertheless", "indeed", "essentially", "fundamentally", "ultimately",
    "specifically", "certainly", "notably", "accordingly",
]

CATEGORY_H_EMPTY_INTENSIFIERS = [
    "truly", "genuinely", "simply", "fundamentally", "undoubtedly",
    "absolutely", "completely", "entirely", "particularly",
]

CATEGORY_I_VAGUE_HEDGING = [
    "it's worth noting that", "it is worth noting that",
    "it's important to note", "it is important to note",
    "it's important to consider", "it is important to consider",
    "it's worth considering", "it is worth considering",
    "one could argue", "some might say", "this could potentially",
]

CATEGORY_J_SYMBOLIC_VERBS = [
    "represents", "reflects", "embodies", "signifies", "exemplifies",
    "underscores", "highlights", "emphasizes", "illustrates", "demonstrates",
    "speaks to", "speaks volumes about",
]

CATEGORY_M_ING_OPENERS = [
    "Highlighting", "Emphasizing", "Facilitating", "Driving", "Enabling",
    "Empowering", "Leveraging", "Showcasing",
]

# ============================================================
# Punctuation thresholds (Category K)
# ============================================================
EM_DASH_DECK_LIMIT = 2
FRAGMENT_COLON_LIMIT = 3

# Deck-level construction phrases to count (D)
FROM_X_TO_Y_LIMIT = 3
WHETHER_X_OR_Y_LIMIT = 3
