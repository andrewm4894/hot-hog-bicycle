"""
Tools the challenger and judge can optionally call.

PostHog LLM Analytics auto-extracts `$ai_tools_called` from the wrapped
OpenAI client's responses, so these show up in the Tools tab with zero
extra instrumentation.

Kept deterministic-with-a-random-pick so there are no external deps and
tool latency stays effectively zero.
"""
import json
import random


# --- Tool data ---------------------------------------------------------

HOT_DOG_FACTS = [
    "The world's longest hot dog was 668 feet 7.62 inches, made in Paraguay in 2011.",
    "Americans eat about 20 billion hot dogs a year — roughly 70 per person.",
    "The hot dog was popularized at Coney Island in 1867 by Charles Feltman.",
    "Nathan's Famous Hot Dog Eating Contest has been held on July 4th since 1916.",
    "Hot dogs were one of the first foods eaten on the Moon — carried by Apollo 11.",
    "A 'Chicago-style' hot dog is famously never served with ketchup.",
    "The dachshund sausage was renamed 'hot dog' after a 1900s cartoonist couldn't spell it.",
    "Frankfurters are named after Frankfurt, Germany, where they were invented in 1487.",
]

BICYCLE_FACTS = [
    "The first pedal-driven bicycle was built by Kirkpatrick Macmillan in 1839.",
    "There are more than a billion bicycles in the world — twice as many as cars.",
    "The penny-farthing got its name from the comparative size of two British coins.",
    "The Netherlands has more bicycles than people.",
    "The longest tandem bicycle ever built seated 35 riders and was over 20 meters long.",
    "Bicycles were called 'dandy horses' when they had no pedals and were pushed along the ground.",
    "The Tour de France was first held in 1903 and covered 2,428 km over six stages.",
    "A standard bike wheel has 32 or 36 spokes — always in a crosshatched lacing pattern.",
]

ART_STYLES = [
    {"name": "Bauhaus", "description": "clean geometric shapes, primary colors, minimal ornament"},
    {"name": "Art Deco", "description": "bold symmetry, gold accents, stylized streamlined forms"},
    {"name": "Cubism", "description": "fragmented planes, multiple viewpoints, muted palette"},
    {"name": "Pop Art", "description": "flat bold colors, thick outlines, comic-book dot shading"},
    {"name": "Memphis", "description": "squiggles, confetti, 80s pastels plus black"},
    {"name": "Vaporwave", "description": "magenta and cyan gradients, grid horizons, retro-futurism"},
    {"name": "Ukiyo-e", "description": "flat areas of color, strong outlines, woodblock-print feel"},
    {"name": "Brutalist", "description": "heavy blocks, raw shapes, monochrome with one accent color"},
    {"name": "Minimalism", "description": "few shapes, lots of whitespace, one or two colors"},
    {"name": "Surrealism", "description": "dream logic, impossible proportions, soft shadows"},
]

COLOR_PALETTES = {
    "classic-condiments": ["#FFDD00", "#D62828", "#6B4423", "#FFF5E1"],  # mustard / ketchup / bun / light bun
    "relish-and-onion":   ["#3CB371", "#FFFFFF", "#D62828", "#FFDD00"],
    "sunset-cyclist":     ["#FF6B35", "#F7C59F", "#EFEFD0", "#004E89", "#1A659E"],
    "neon-night":         ["#FF00E5", "#00FFFF", "#1A1A2E", "#FFFF00"],
    "vintage-americana":  ["#B5121B", "#F9E0A9", "#284B63", "#3C3C3B"],
    "monochrome-pop":     ["#000000", "#FFFFFF", "#FF4136"],
    "forest-picnic":      ["#355E3B", "#8B4513", "#FFDD00", "#F5DEB3"],
    "retro-diner":        ["#E63946", "#F1FAEE", "#A8DADC", "#457B9D"],
}

COMPOSITION_IDEAS = [
    "dramatic low-angle shot, bicycle filling the frame from below",
    "isometric 3/4 view, like a video game tile",
    "silhouette against a sunset, high contrast",
    "close-up on the front wheel with the hot dog leaning in",
    "side profile, bicycle mid-air over a small jump",
    "overhead top-down view, circular composition",
    "wide establishing shot, hot dog tiny against a huge landscape",
    "symmetrical front-on portrait, bicycle aimed at viewer",
    "action blur streaks behind a speeding hot dog",
    "storybook tableau, hot dog pedaling past friendly shops",
]

CRITIC_PERSONAS = [
    {"name": "grumpy food critic",        "voice": "dismissive, hungry, sarcastic, writes like a tired restaurant reviewer"},
    {"name": "earnest art curator",       "voice": "sincere, uses gallery language, takes the work seriously even if silly"},
    {"name": "bored teenager",            "voice": "monosyllabic, unimpressed, slang-heavy, lowercase"},
    {"name": "overcaffeinated coach",     "voice": "loud, motivational, uses exclamation points, sports metaphors"},
    {"name": "Victorian poet",            "voice": "flowery, archaic, dramatic metaphors about wheels and sausages"},
    {"name": "competitive cyclist",       "voice": "judges everything by aerodynamics and gear ratios"},
    {"name": "German engineer",           "voice": "precise, structural, critiques the SVG like it's a machine"},
    {"name": "toddler who just woke up",  "voice": "short sentences, random capitalization, weirdly profound"},
]


# --- Tool implementations ---------------------------------------------

def _get_hot_dog_fact() -> dict:
    return {"fact": random.choice(HOT_DOG_FACTS)}


def _get_bicycle_fact() -> dict:
    return {"fact": random.choice(BICYCLE_FACTS)}


def _get_art_style() -> dict:
    return random.choice(ART_STYLES)


def _get_color_palette(theme: str | None = None) -> dict:
    if theme and theme in COLOR_PALETTES:
        return {"theme": theme, "colors": COLOR_PALETTES[theme]}
    theme = random.choice(list(COLOR_PALETTES.keys()))
    return {"theme": theme, "colors": COLOR_PALETTES[theme]}


def _get_composition_idea() -> dict:
    return {"idea": random.choice(COMPOSITION_IDEAS)}


def _get_critic_persona() -> dict:
    return random.choice(CRITIC_PERSONAS)


# --- OpenAI-format tool specs -----------------------------------------

_PALETTE_ENUM = list(COLOR_PALETTES.keys())

CHALLENGER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_hot_dog_fact",
            "description": "Get a random hot dog trivia fact for inspiration. Call this if you want a real-world detail to work into your prompt.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bicycle_fact",
            "description": "Get a random bicycle trivia fact for inspiration. Useful for grounding your prompt in a bicycle detail.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_art_style",
            "description": "Get a random art movement (e.g. Bauhaus, Pop Art) with a short style description. Call this if you want to commit the SVG to a specific visual style.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_color_palette",
            "description": "Get a themed hex color palette. Optionally request a specific theme; otherwise a random palette is returned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "description": "Optional palette theme name.",
                        "enum": _PALETTE_ENUM,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_composition_idea",
            "description": "Get a random composition/camera-angle suggestion to shape how the SVG is framed.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]

APPEAL_DECISION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_appeal",
            "description": (
                "File an appeal against the judge's ruling with the Supreme Hot Dog Court. "
                "Only call this if you genuinely believe the ruling was unfair and your SVG "
                "deserved better. If you accept the ruling, do NOT call this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plea": {
                        "type": "string",
                        "description": "Your passionate argument (max 500 chars) for why the ruling should be overturned.",
                    },
                },
                "required": ["plea"],
                "additionalProperties": False,
            },
        },
    },
]

JUDGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_critic_persona",
            "description": "Get a random critic persona to adopt for your roasts (e.g. grumpy food critic, Victorian poet). Call this before judging to give your commentary a specific voice.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]

TOOL_IMPLS = {
    "get_hot_dog_fact": _get_hot_dog_fact,
    "get_bicycle_fact": _get_bicycle_fact,
    "get_art_style": _get_art_style,
    "get_color_palette": _get_color_palette,
    "get_composition_idea": _get_composition_idea,
    "get_critic_persona": _get_critic_persona,
}


def execute_tool(name: str, arguments_json: str) -> str:
    """Run a tool by name with JSON-string arguments; always returns a string."""
    fn = TOOL_IMPLS.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}
    try:
        result = fn(**args)
    except TypeError:
        # Model passed bad args — retry with no args so the tool still resolves.
        result = fn()
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps(result)
