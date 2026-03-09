"""
PetCircle Phase 1 — Breed Normalizer

Maps common abbreviations, nicknames, and misspellings of dog and cat
breeds to their standardized names. Applied during onboarding when
the user enters a breed.

Rules:
    - Matching is case-insensitive.
    - If no match is found, the original input is title-cased and returned.
    - Covers the most popular breeds in India plus common global breeds.
"""


import re
from difflib import get_close_matches

# ----------------------------------
# Runtime learning layer
# ----------------------------------

_LEARNED_ALIASES: dict[str, str] = {}


# ----------------------------------
# DOG BREEDS (full dataset)
# ----------------------------------

_DOG_BREEDS: dict[str, str] = {

    # Labrador Retriever
    "lab": "Labrador Retriever",
    "labrador": "Labrador Retriever",
    "labrador retriever": "Labrador Retriever",
    "labra": "Labrador Retriever",
    "black lab": "Labrador Retriever",
    "yellow lab": "Labrador Retriever",
    "chocolate lab": "Labrador Retriever",

    # Golden Retriever
    "golden": "Golden Retriever",
    "golden retriever": "Golden Retriever",
    "goldie": "Golden Retriever",

    # German Shepherd
    "gsd": "German Shepherd",
    "german shepherd": "German Shepherd",
    "german shepard": "German Shepherd",
    "germanshepherd": "German Shepherd",
    "g shepherd": "German Shepherd",
    "alsatian": "German Shepherd",

    # Husky
    "husky": "Siberian Husky",
    "siberian husky": "Siberian Husky",
    "sibe": "Siberian Husky",

    # Rottweiler
    "rottweiler": "Rottweiler",
    "rottie": "Rottweiler",
    "rotweiler": "Rottweiler",
    "rotweiller": "Rottweiler",

    # Doberman
    "doberman": "Doberman Pinscher",
    "doberman pinscher": "Doberman Pinscher",
    "dobie": "Doberman Pinscher",

    # Dachshund
    "dachshund": "Dachshund",
    "dashund": "Dachshund",
    "dachund": "Dachshund",
    "doxie": "Dachshund",
    "wiener dog": "Dachshund",
    "sausage dog": "Dachshund",

    # Shih Tzu
    "shih tzu": "Shih Tzu",
    "shihtzu": "Shih Tzu",
    "shitzu": "Shih Tzu",

    # Pomeranian
    "pomeranian": "Pomeranian",
    "pom": "Pomeranian",
    "pomarian": "Pomeranian",
    "pomernian": "Pomeranian",

    # Chihuahua
    "chihuahua": "Chihuahua",
    "chi": "Chihuahua",

    # Yorkshire Terrier
    "yorkshire terrier": "Yorkshire Terrier",
    "yorkie": "Yorkshire Terrier",

    # Maltese
    "maltese": "Maltese",

    # Border Collie
    "border collie": "Border Collie",
    "collie": "Border Collie",

    # Jack Russell
    "jack russell": "Jack Russell Terrier",
    "jack russell terrier": "Jack Russell Terrier",
    "jrt": "Jack Russell Terrier",

    # Cane Corso
    "cane corso": "Cane Corso",
    "corso": "Cane Corso",

    # Pit Bull
    "pitbull": "American Pit Bull Terrier",
    "pit bull": "American Pit Bull Terrier",
    "pittie": "American Pit Bull Terrier",

    # Mixed
    "mixed": "Mixed Breed",
    "mixed breed": "Mixed Breed",
    "mutt": "Mixed Breed",
    "lab mix": "Mixed Breed",
    "husky mix": "Mixed Breed",

    # Indian dogs
    "indie": "Indian Pariah Dog",
    "indian pariah": "Indian Pariah Dog",
    "desi": "Indian Pariah Dog",
    "street dog": "Indian Pariah Dog",
}


# ----------------------------------
# CAT BREEDS
# ----------------------------------

_CAT_BREEDS: dict[str, str] = {

    # Persian
    "persian": "Persian",
    "persian cat": "Persian",
    "persi": "Persian",
    "persain": "Persian",

    # Siamese
    "siamese": "Siamese",
    "siamise": "Siamese",

    # Maine Coon
    "maine coon": "Maine Coon",
    "mainecoon": "Maine Coon",
    "coon": "Maine Coon",

    # Ragdoll
    "ragdoll": "Ragdoll",
    "rag doll": "Ragdoll",
    "raggie": "Ragdoll",

    # British Shorthair
    "british shorthair": "British Shorthair",
    "brit": "British Shorthair",
    "british": "British Shorthair",
    "bsh": "British Shorthair",

    # Bengal
    "bengal": "Bengal",

    # Abyssinian
    "abyssinian": "Abyssinian",
    "aby": "Abyssinian",

    # Sphynx
    "sphynx": "Sphynx",
    "sphinx": "Sphynx",
    "hairless": "Sphynx",

    # Scottish Fold
    "scottish fold": "Scottish Fold",

    # Russian Blue
    "russian blue": "Russian Blue",
    "russian": "Russian Blue",

    # Exotic
    "exotic": "Exotic Shorthair",
    "exotic shorthair": "Exotic Shorthair",

    # Rex
    "cornish rex": "Cornish Rex",
    "rex": "Cornish Rex",
    "devon rex": "Devon Rex",
    "devon": "Devon Rex",

    # Norwegian Forest
    "norwegian forest cat": "Norwegian Forest Cat",
    "wegie": "Norwegian Forest Cat",

    # Domestic
    "domestic shorthair": "Domestic Shorthair",
    "dsh": "Domestic Shorthair",
    "domestic longhair": "Domestic Longhair",
    "dlh": "Domestic Longhair",

    # Tabby
    "tabby": "Tabby",
    "orange tabby": "Tabby",
    "ginger tabby": "Tabby",
    "gray tabby": "Tabby",

    # Indian
    "indie": "Indian Domestic Cat",
    "desi": "Indian Domestic Cat",
    "street cat": "Indian Domestic Cat",
}


_ALL_BREEDS = {**_DOG_BREEDS, **_CAT_BREEDS}


# ----------------------------------
# NORMALIZER
# ----------------------------------

def normalize_breed(breed: str, species: str | None = None) -> str:

    if not breed:
        return breed

    original = breed
    key = breed.lower().strip()

    # remove punctuation
    key = re.sub(r"[^a-z\s]", "", key)

    # remove noise words
    for word in ["dog", "cat", "puppy", "kitten", "breed"]:
        key = key.replace(word, "")

    key = key.strip()

    # detect mix
    if "mix" in original.lower():
        return "Mixed Breed"

    # learned aliases
    if key in _LEARNED_ALIASES:
        return _LEARNED_ALIASES[key]

    # species specific
    if species == "dog" and key in _DOG_BREEDS:
        return _DOG_BREEDS[key]

    if species == "cat" and key in _CAT_BREEDS:
        return _CAT_BREEDS[key]

    # global exact
    if key in _ALL_BREEDS:
        return _ALL_BREEDS[key]

    # fuzzy
    matches = get_close_matches(key, _ALL_BREEDS.keys(), n=1, cutoff=0.85)

    if matches:
        canonical = _ALL_BREEDS[matches[0]]

        # learn new alias
        _LEARNED_ALIASES[key] = canonical

        return canonical

    # No match found — return title-cased original for now.
    # Caller can use normalize_breed_with_ai() as async fallback.
    return original.strip().title()


async def normalize_breed_with_ai(breed: str, species: str | None = None) -> str:
    """
    Use OpenAI to identify a breed when the local normalizer fails.

    Called as an async fallback during onboarding when the user's input
    doesn't match any known breed abbreviation or fuzzy match.

    Args:
        breed: The raw breed text from the user.
        species: "dog" or "cat" for context.

    Returns:
        The standardized breed name, or "Mixed Breed" if unidentifiable.
    """
    import logging
    from openai import AsyncOpenAI
    from app.config import settings
    from app.core.constants import OPENAI_QUERY_MODEL

    logger = logging.getLogger(__name__)

    animal = species or "pet"
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = await client.chat.completions.create(
            model=OPENAI_QUERY_MODEL,
            temperature=0.0,
            max_tokens=30,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a {animal} breed identifier. The user will provide text "
                        f"that may be a breed name, abbreviation, misspelling, or local name. "
                        f"Identify the standardized {animal} breed name and return ONLY the "
                        f"breed name. If it's clearly a mixed breed, return 'Mixed Breed'. "
                        f"If you cannot identify any breed, return 'UNKNOWN'."
                    ),
                },
                {"role": "user", "content": breed},
            ],
        )

        result = response.choices[0].message.content.strip()

        if result == "UNKNOWN":
            return breed.strip().title()

        # Learn the alias for future lookups.
        key = breed.lower().strip()
        _LEARNED_ALIASES[key] = result

        return result

    except Exception as e:
        logger.error("AI breed identification failed for '%s': %s", breed, str(e))
        return breed.strip().title()