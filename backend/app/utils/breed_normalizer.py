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


# Mapping of lowercase aliases → canonical breed name.
# Each key is a common abbreviation, nickname, or misspelling.
_DOG_BREEDS: dict[str, str] = {
    # Labrador Retriever
    "lab": "Labrador Retriever",
    "labrador": "Labrador Retriever",
    "labrador retriever": "Labrador Retriever",
    "labra": "Labrador Retriever",
    "labi": "Labrador Retriever",
    # Golden Retriever
    "golden": "Golden Retriever",
    "golden retriever": "Golden Retriever",
    "goldie": "Golden Retriever",
    # German Shepherd
    "gsd": "German Shepherd",
    "german shepherd": "German Shepherd",
    "german shepard": "German Shepherd",
    "german shepherd dog": "German Shepherd",
    "alsatian": "German Shepherd",
    # Beagle
    "beagle": "Beagle",
    # Pug
    "pug": "Pug",
    "vodafone dog": "Pug",
    # Rottweiler
    "rottweiler": "Rottweiler",
    "rottie": "Rottweiler",
    "rott": "Rottweiler",
    "rotweiler": "Rottweiler",
    # Doberman
    "doberman": "Doberman Pinscher",
    "doberman pinscher": "Doberman Pinscher",
    "dobie": "Doberman Pinscher",
    # Boxer
    "boxer": "Boxer",
    # Dachshund
    "dachshund": "Dachshund",
    "sausage dog": "Dachshund",
    "wiener dog": "Dachshund",
    "doxie": "Dachshund",
    # Shih Tzu
    "shih tzu": "Shih Tzu",
    "shihtzu": "Shih Tzu",
    "shitzu": "Shih Tzu",
    # Pomeranian
    "pomeranian": "Pomeranian",
    "pom": "Pomeranian",
    # Husky
    "husky": "Siberian Husky",
    "siberian husky": "Siberian Husky",
    # Cocker Spaniel
    "cocker spaniel": "Cocker Spaniel",
    "cocker": "Cocker Spaniel",
    # Lhasa Apso
    "lhasa apso": "Lhasa Apso",
    "lhasa": "Lhasa Apso",
    # Great Dane
    "great dane": "Great Dane",
    "dane": "Great Dane",
    # Dalmatian
    "dalmatian": "Dalmatian",
    # Saint Bernard
    "saint bernard": "Saint Bernard",
    "st bernard": "Saint Bernard",
    "st. bernard": "Saint Bernard",
    # Bulldog
    "bulldog": "Bulldog",
    "english bulldog": "English Bulldog",
    "french bulldog": "French Bulldog",
    "frenchie": "French Bulldog",
    # Pit Bull
    "pitbull": "American Pit Bull Terrier",
    "pit bull": "American Pit Bull Terrier",
    "pittie": "American Pit Bull Terrier",
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
    # Poodle
    "poodle": "Poodle",
    "toy poodle": "Toy Poodle",
    "standard poodle": "Standard Poodle",
    "mini poodle": "Miniature Poodle",
    "miniature poodle": "Miniature Poodle",
    # Indian breeds
    "indie": "Indian Pariah Dog",
    "indian pariah": "Indian Pariah Dog",
    "indian pariah dog": "Indian Pariah Dog",
    "desi": "Indian Pariah Dog",
    "desi dog": "Indian Pariah Dog",
    "street dog": "Indian Pariah Dog",
    "stray": "Indian Pariah Dog",
    "mudhol hound": "Mudhol Hound",
    "rajapalayam": "Rajapalayam",
    "kanni": "Kanni",
    "chippiparai": "Chippiparai",
    "kombai": "Kombai",
    # Mixed
    "mixed": "Mixed Breed",
    "mixed breed": "Mixed Breed",
    "mutt": "Mixed Breed",
    "crossbreed": "Mixed Breed",
    "cross": "Mixed Breed",
    # Spitz
    "spitz": "Indian Spitz",
    "indian spitz": "Indian Spitz",
    # Cavalier King Charles
    "cavalier": "Cavalier King Charles Spaniel",
    "cavalier king charles": "Cavalier King Charles Spaniel",
    # Schnauzer
    "schnauzer": "Schnauzer",
    "mini schnauzer": "Miniature Schnauzer",
    "miniature schnauzer": "Miniature Schnauzer",
    # Australian Shepherd
    "aussie": "Australian Shepherd",
    "australian shepherd": "Australian Shepherd",
    # Corgi
    "corgi": "Pembroke Welsh Corgi",
    "pembroke corgi": "Pembroke Welsh Corgi",
    # Akita
    "akita": "Akita",
    # Bernese
    "bernese": "Bernese Mountain Dog",
    "bernese mountain dog": "Bernese Mountain Dog",
    # Cane Corso
    "cane corso": "Cane Corso",
    # Shiba Inu
    "shiba": "Shiba Inu",
    "shiba inu": "Shiba Inu",
    # Bichon Frise
    "bichon": "Bichon Frise",
    "bichon frise": "Bichon Frise",
    # Weimaraner
    "weimaraner": "Weimaraner",
    # Mastiff
    "mastiff": "Mastiff",
    "english mastiff": "English Mastiff",
    "bull mastiff": "Bullmastiff",
    "bullmastiff": "Bullmastiff",
}

_CAT_BREEDS: dict[str, str] = {
    # Persian
    "persian": "Persian",
    "persian cat": "Persian",
    "persi": "Persian",
    # Siamese
    "siamese": "Siamese",
    # Maine Coon
    "maine coon": "Maine Coon",
    "mainecoon": "Maine Coon",
    # Ragdoll
    "ragdoll": "Ragdoll",
    "rag doll": "Ragdoll",
    # British Shorthair
    "british shorthair": "British Shorthair",
    "british blue": "British Shorthair",
    # Bengal
    "bengal": "Bengal",
    "bengal cat": "Bengal",
    # Abyssinian
    "abyssinian": "Abyssinian",
    "aby": "Abyssinian",
    # Sphynx
    "sphynx": "Sphynx",
    "sphinx": "Sphynx",
    "hairless cat": "Sphynx",
    # Scottish Fold
    "scottish fold": "Scottish Fold",
    # Russian Blue
    "russian blue": "Russian Blue",
    # Bombay
    "bombay": "Bombay",
    "bombay cat": "Bombay",
    # Himalayan
    "himalayan": "Himalayan",
    # Exotic Shorthair
    "exotic shorthair": "Exotic Shorthair",
    "exotic": "Exotic Shorthair",
    # Indian breeds / mixed
    "indie": "Indian Domestic Cat",
    "indie cat": "Indian Domestic Cat",
    "desi": "Indian Domestic Cat",
    "desi cat": "Indian Domestic Cat",
    "street cat": "Indian Domestic Cat",
    "stray": "Indian Domestic Cat",
    "mixed": "Mixed Breed",
    "mixed breed": "Mixed Breed",
    "domestic shorthair": "Domestic Shorthair",
    "dsh": "Domestic Shorthair",
    "tabby": "Tabby",
    # Birman
    "birman": "Birman",
    # Burmese
    "burmese": "Burmese",
    # Turkish Angora
    "turkish angora": "Turkish Angora",
    "angora": "Turkish Angora",
    # Munchkin
    "munchkin": "Munchkin",
    # Tonkinese
    "tonkinese": "Tonkinese",
    # American Shorthair
    "american shorthair": "American Shorthair",
    # Savannah
    "savannah": "Savannah",
    "savannah cat": "Savannah",
}

# Combined lookup for species-agnostic normalization.
_ALL_BREEDS = {**_DOG_BREEDS, **_CAT_BREEDS}


def normalize_breed(breed: str, species: str | None = None) -> str:
    """
    Normalize a breed name to its canonical form.

    Looks up the breed in a species-specific dictionary first (if species
    is provided), then falls back to the combined dictionary. If no match
    is found, the original input is title-cased.

    Args:
        breed: The user-entered breed string.
        species: Optional species ('dog' or 'cat') for more accurate matching.

    Returns:
        The normalized breed name.
    """
    key = breed.strip().lower()

    if not key:
        return breed

    # Try species-specific lookup first for accuracy.
    if species == "dog" and key in _DOG_BREEDS:
        return _DOG_BREEDS[key]
    if species == "cat" and key in _CAT_BREEDS:
        return _CAT_BREEDS[key]

    # Fall back to combined lookup.
    if key in _ALL_BREEDS:
        return _ALL_BREEDS[key]

    # No match — title-case the input for consistent display.
    return breed.strip().title()
