"""
PetCircle Phase 1 — Breed Fun Facts

Returns a unique fun fact about a pet's breed to include in document
acknowledgment messages. Tracks shown facts per user to avoid repeats.

When a breed is not in the local database, generates facts via OpenAI
(gpt-4.1-mini) and caches them in memory.

Falls back to generic species facts if both local DB and OpenAI fail.
"""

import hashlib
import json
import logging
import random
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.core.constants import OPENAI_QUERY_MODEL
from app.models.shown_fun_fact import ShownFunFact

logger = logging.getLogger(__name__)

# --- In-memory cache for AI-generated facts (per breed key) ---
# Avoids repeated OpenAI calls for the same unknown breed.
_AI_GENERATED_FACTS: dict[str, list[str]] = {}

# --- Cached OpenAI client (lazy init, same pattern as query_engine) ---
_openai_fun_fact_client = None


def _get_openai_client():
    """Return a cached AsyncOpenAI client for fun fact generation."""
    global _openai_fun_fact_client
    if _openai_fun_fact_client is None:
        from openai import AsyncOpenAI
        _openai_fun_fact_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_fun_fact_client


def _hash_fact(fact: str) -> str:
    """Return SHA-256 hex digest of a fact string."""
    return hashlib.sha256(fact.encode("utf-8")).hexdigest()


def _dedupe_facts(facts: list[str]) -> list[str]:
    """Return facts in original order with duplicates removed."""
    seen: set[str] = set()
    unique_facts: list[str] = []
    for fact in facts:
        normalized = fact.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_facts.append(normalized)
    return unique_facts

# ----------------------------------
# DOG BREED FUN FACTS
# ----------------------------------

_DOG_FACTS: dict[str, list[str]] = {
    "Labrador Retriever": [
        "Labs have a special waterproof double coat and webbed toes — born swimmers!",
        "Labradors are the most popular dog breed in the world for over 30 years running.",
        "A Lab's nose has up to 300 million scent receptors — that's 40x more than humans!",
    ],
    "Golden Retriever": [
        "Golden Retrievers have such soft mouths they can carry a raw egg without breaking it.",
        "Goldens were originally bred in Scotland to retrieve waterfowl for hunters.",
        "Golden Retrievers stay puppy-like in personality well into their senior years!",
    ],
    "German Shepherd": [
        "German Shepherds can learn a new command in just 5 repetitions!",
        "GSDs were the first-ever guide dogs for the blind.",
        "A German Shepherd's bite force is around 238 PSI — one of the strongest among dogs.",
    ],
    "Siberian Husky": [
        "Huskies can change their metabolism to run for hours without getting tired!",
        "A team of Huskies ran 674 miles in 1925 to deliver life-saving medicine to Nome, Alaska.",
        "Huskies have a special inner eyelid that protects their eyes from snow glare.",
    ],
    "Rottweiler": [
        "Rottweilers were originally used to pull butcher carts in Germany!",
        "Rotties are one of the oldest herding breeds, dating back to Roman times.",
        "Despite their tough look, Rottweilers are known to be gentle goofballs at home.",
    ],
    "Doberman Pinscher": [
        "Dobermans were created by a German tax collector who wanted a loyal guard dog!",
        "Dobermans are one of the top 5 most intelligent dog breeds in the world.",
        "A Doberman named Kurt was the first canine casualty of WWII — a true war hero.",
    ],
    "Dachshund": [
        "Dachshunds were bred to hunt badgers — 'Dachs' means badger in German!",
        "A Dachshund named Waldi was the first-ever Olympic mascot (Munich 1972).",
        "Despite their size, Dachshunds have one of the loudest barks among small breeds.",
    ],
    "Shih Tzu": [
        "Shih Tzus were bred as palace pets for Chinese emperors!",
        "The name 'Shih Tzu' means 'little lion' in Mandarin.",
        "Every Shih Tzu alive today can be traced to just 14 dogs that saved the breed.",
    ],
    "Pomeranian": [
        "Pomeranians descended from large Arctic sled dogs — they were once 30+ pounds!",
        "Two Pomeranians survived the sinking of the Titanic.",
        "Mozart, Michelangelo, and Queen Victoria all had Pomeranians!",
    ],
    "Chihuahua": [
        "Chihuahuas have the largest brain-to-body ratio of any dog breed!",
        "They're named after the state of Chihuahua in Mexico.",
        "Chihuahuas can live up to 20 years — one of the longest lifespans among dogs.",
    ],
    "Yorkshire Terrier": [
        "Yorkies were originally bred to catch rats in clothing mills!",
        "A Yorkie named Smoky is considered the first therapy dog in history.",
        "Despite their tiny size, Yorkies are fearless and full of terrier attitude.",
    ],
    "Maltese": [
        "The Maltese is one of the most ancient breeds — over 2,000 years old!",
        "Ancient Greeks built tombs for their Maltese dogs.",
        "Maltese don't shed because they have hair, not fur!",
    ],
    "Border Collie": [
        "Border Collies are considered the smartest dog breed in the world!",
        "A Border Collie named Chaser learned over 1,000 words.",
        "They can control sheep with just an intense stare called 'the eye'.",
    ],
    "Jack Russell Terrier": [
        "Jack Russells can jump up to 5 feet high — that's 5x their own height!",
        "They were bred by Reverend John Russell for fox hunting in the 1800s.",
        "A Jack Russell named Uggie starred in the Oscar-winning film 'The Artist'.",
    ],
    "Cane Corso": [
        "Cane Corsos were used as war dogs by the ancient Romans!",
        "Their name comes from Latin 'cohors' meaning guardian or protector.",
        "Despite their size, Cane Corsos are known for being surprisingly gentle with kids.",
    ],
    "American Pit Bull Terrier": [
        "Pit Bulls were once known as 'nanny dogs' for being so gentle with children.",
        "Sergeant Stubby, a Pit Bull, is the most decorated war dog in US history.",
        "Pit Bulls consistently score high on temperament tests — over 87%!",
    ],
    "Mixed Breed": [
        "Mixed breeds often benefit from 'hybrid vigor' — fewer genetic health issues!",
        "Every mixed breed is truly one-of-a-kind — there's no other dog exactly like yours.",
        "Mixed breed dogs have been shown to live 1-2 years longer on average.",
    ],
    "Indian Pariah Dog": [
        "Indian Pariah Dogs are one of the oldest and healthiest breeds in the world!",
        "They have a natural immunity to many diseases that affect purebreds.",
        "Pariah Dogs have been companions to humans in India for over 4,500 years.",
    ],
}

# ----------------------------------
# CAT BREED FUN FACTS
# ----------------------------------

_CAT_FACTS: dict[str, list[str]] = {
    "Persian": [
        "Persians are one of the oldest cat breeds, dating back to 1684!",
        "Queen Victoria owned two Persian cats — making them royally popular.",
        "Persian cats spend up to 16-20 hours a day sleeping. Living the dream!",
    ],
    "Siamese": [
        "Siamese cats are one of the most vocal breeds — they love to 'talk'!",
        "They're born completely white and develop color points as they grow.",
        "Siamese cats were once sacred temple cats in Thailand.",
    ],
    "Maine Coon": [
        "Maine Coons are the largest domestic cat breed — some weigh over 11 kg!",
        "They have water-resistant fur and love playing with water.",
        "A Maine Coon named Stewie holds the record for longest domestic cat at 123 cm!",
    ],
    "Ragdoll": [
        "Ragdolls get their name because they go completely limp when you pick them up!",
        "They're often called 'puppy cats' because they follow their owners around.",
        "Ragdolls are one of the largest cat breeds but also one of the gentlest.",
    ],
    "British Shorthair": [
        "The Cheshire Cat from Alice in Wonderland was inspired by a British Shorthair!",
        "They're one of the oldest known cat breeds in the world.",
        "British Shorthairs are known for their adorable round faces and chunky bodies.",
    ],
    "Bengal": [
        "Bengals have a unique 'glitter' gene that makes their fur shimmer in light!",
        "They're one of the few cat breeds that genuinely enjoy water.",
        "Bengals were created by crossing domestic cats with Asian Leopard Cats.",
    ],
    "Sphynx": [
        "Sphynx cats aren't truly hairless — they're covered in a fine peach-fuzz!",
        "They have the warmest body temperature of any cat breed.",
        "Sphynx cats are incredibly social and are often described as 'part monkey, part dog'.",
    ],
    "Scottish Fold": [
        "Scottish Folds get their folded ears from a natural genetic mutation.",
        "Taylor Swift's cats Meredith and Olivia are Scottish Folds!",
        "They're known for sitting in a funny 'Buddha position' with legs stretched out.",
    ],
    "Russian Blue": [
        "Russian Blues are believed to bring good luck in Russian folklore!",
        "They have a unique double coat that stands out at a 45-degree angle.",
        "Russian Blues are so clean they're sometimes called 'the cat of royalty'.",
    ],
    "Tabby": [
        "The 'M' marking on a Tabby's forehead is one of nature's coolest patterns!",
        "Tabbies aren't a breed — it's a coat pattern found across many breeds.",
        "About 80% of all cats in the world have some form of tabby markings.",
    ],
    "Indian Domestic Cat": [
        "Indian domestic cats are incredibly resilient and adaptable!",
        "They've been companions in Indian households for thousands of years.",
        "Indian cats are known for their street-smart intelligence and hardy health.",
    ],
    "Domestic Shorthair": [
        "Domestic Shorthairs make up about 90% of all cats in the world!",
        "No two Domestic Shorthairs are exactly alike — each one is unique.",
        "They're considered one of the healthiest cat 'breeds' due to their genetic diversity.",
    ],
    "Domestic Longhair": [
        "Domestic Longhairs come in every possible color and pattern!",
        "Their long fur originally evolved to keep them warm in cold climates.",
        "They're like Domestic Shorthairs but with extra floof and personality!",
    ],
}

# ----------------------------------
# GENERIC FALLBACKS
# ----------------------------------

_GENERIC_DOG_FACTS = [
    "Dogs can understand up to 250 words and gestures!",
    "A dog's nose print is unique, just like a human fingerprint.",
    "Dogs dream just like humans — those twitchy paws mean they're chasing something!",
    "Dogs can smell your feelings — they detect changes in human emotions through scent.",
    "A dog's sense of smell is 10,000 to 100,000 times more sensitive than ours!",
]

_GENERIC_CAT_FACTS = [
    "Cats spend 70% of their lives sleeping. Goals!",
    "A group of cats is called a 'clowder'.",
    "Cats have over 20 different vocalizations, including the purr, which can heal bones!",
    "Cats can rotate their ears 180 degrees — built-in radar!",
    "A cat's purr vibrates at 25-150 Hz — frequencies that promote healing.",
]


async def _generate_breed_facts_with_ai(breed: str, species: str) -> list[str]:
    """
    Generate 3 fun facts about a breed using OpenAI (gpt-4.1-mini).

    Results are cached in _AI_GENERATED_FACTS so subsequent calls
    for the same breed don't hit the API again.

    Args:
        breed: The breed name.
        species: "dog" or "cat".

    Returns:
        List of 3 fact strings, or empty list on failure.
    """
    cache_key = f"{species}:{breed}"
    if cache_key in _AI_GENERATED_FACTS:
        return _AI_GENERATED_FACTS[cache_key]

    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=OPENAI_QUERY_MODEL,
            temperature=0.8,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate short, fun, surprising facts about pet breeds. "
                        "Return a JSON array of exactly 3 strings. No markdown, no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Generate 3 short, fun, surprising facts about {breed} {species}s.",
                },
            ],
        )
        raw = response.choices[0].message.content.strip()
        facts = json.loads(raw)
        if isinstance(facts, list) and len(facts) >= 1:
            facts = _dedupe_facts([str(f) for f in facts[:3]])
            _AI_GENERATED_FACTS[cache_key] = facts
            logger.info("Generated %d AI fun facts for breed=%s species=%s", len(facts), breed, species)
            return facts
    except Exception:
        logger.warning("Failed to generate AI fun facts for breed=%s species=%s", breed, species, exc_info=True)

    return []


async def _generate_additional_fun_facts_with_ai(
    breed: str | None,
    species: str,
    excluded_facts: list[str],
    count: int = 5,
) -> list[str]:
    """
    Generate additional unseen fun facts after the known pool is exhausted.

    This bypasses the in-memory cache because the prompt depends on which facts
    the user has already seen.
    """
    try:
        client = _get_openai_client()
        subject = f"the {breed} breed" if breed else f"{species}s"
        excluded_list = "\n".join(f"- {fact}" for fact in excluded_facts)
        response = await client.chat.completions.create(
            model=OPENAI_QUERY_MODEL,
            temperature=0.9,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate short, fun, surprising facts about pets. "
                        f"Return a JSON array of exactly {count} unique strings. "
                        "No markdown and no extra text. Do not repeat or closely paraphrase excluded facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate {count} short, fun, surprising facts about {subject}.\n"
                        "Avoid repeating any of these facts:\n"
                        f"{excluded_list or '- None provided'}"
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content.strip()
        facts = json.loads(raw)
        if isinstance(facts, list) and facts:
            excluded_set = {fact.strip() for fact in excluded_facts}
            new_facts = [
                fact for fact in _dedupe_facts([str(f) for f in facts])
                if fact not in excluded_set
            ]
            logger.info(
                "Generated %d additional AI fun facts for breed=%s species=%s",
                len(new_facts),
                breed,
                species,
            )
            return new_facts
    except Exception:
        logger.warning(
            "Failed to generate additional AI fun facts for breed=%s species=%s",
            breed,
            species,
            exc_info=True,
        )

    return []


async def get_breed_fun_fact(db: Session, user_id: UUID, breed: str | None, species: str) -> str:
    """
    Return a unique fun fact for the given breed and species.

    Tracks shown facts per user in the shown_fun_facts table so the same
    user does not see the same fact twice. When the built-in pool has been
    exhausted, the function first tries to generate fresh facts before
    falling back to a reset.

    If the breed is not in the local database, generates facts via OpenAI.
    Falls back to generic species facts if everything else fails.

    Args:
        db: SQLAlchemy session.
        user_id: The user's UUID.
        breed: The normalized breed name (e.g. "Labrador Retriever"), or None.
        species: "dog" or "cat".

    Returns:
        A single fun fact string.
    """
    facts_db = _DOG_FACTS if species == "dog" else _CAT_FACTS
    fallback = _GENERIC_DOG_FACTS if species == "dog" else _GENERIC_CAT_FACTS

    # Step 1: Collect candidate facts.
    candidates: list[str] = []
    if breed and breed in facts_db:
        candidates = list(facts_db[breed])
    elif breed:
        # Breed not in local DB — try OpenAI generation.
        ai_facts = await _generate_breed_facts_with_ai(breed, species)
        if ai_facts:
            candidates = ai_facts

    # If no breed-specific candidates, use generic fallback.
    if not candidates:
        candidates = list(fallback)

    # Step 2: Get hashes of facts already shown to this user.
    shown_hashes: set[str] = set()
    try:
        rows = (
            db.query(ShownFunFact.fact_hash)
            .filter(ShownFunFact.user_id == user_id)
            .all()
        )
        shown_hashes = {row.fact_hash for row in rows}
    except Exception:
        logger.warning("Failed to query shown_fun_facts for user_id=%s", user_id, exc_info=True)

    # Step 3: Filter to unseen facts.
    unseen = [f for f in candidates if _hash_fact(f) not in shown_hashes]

    # Step 4: If all built-in facts are exhausted, try generating fresh ones.
    if not unseen:
        extra_candidates = await _generate_additional_fun_facts_with_ai(
            breed=breed,
            species=species,
            excluded_facts=candidates,
        )
        if extra_candidates:
            candidates = _dedupe_facts(candidates + extra_candidates)
            unseen = [f for f in candidates if _hash_fact(f) not in shown_hashes]

    # Step 5: If still exhausted, reset and pick from full list as a last resort.
    if not unseen:
        try:
            candidate_hashes = {_hash_fact(f) for f in candidates}
            db.query(ShownFunFact).filter(
                ShownFunFact.user_id == user_id,
                ShownFunFact.fact_hash.in_(candidate_hashes),
            ).delete(synchronize_session="fetch")
            db.commit()
            logger.info("Reset shown fun facts for user_id=%s (breed=%s)", user_id, breed)
        except Exception:
            db.rollback()
            logger.warning("Failed to reset shown_fun_facts for user_id=%s", user_id, exc_info=True)
        unseen = candidates

    # Step 6: Pick a random fact and record it.
    chosen = random.choice(unseen)
    try:
        db.add(ShownFunFact(user_id=user_id, fact_hash=_hash_fact(chosen)))
        db.commit()
    except Exception:
        # Unique constraint violation or other DB error — non-fatal.
        db.rollback()
        logger.warning("Failed to record shown fun fact for user_id=%s", user_id, exc_info=True)

    return chosen
