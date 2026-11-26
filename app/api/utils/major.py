# app/api/utils/major.py
"""Major mapping, canonical slug normalization, and query filter utilities."""
from typing import Optional

MAJOR_CANONICAL_SLUGS: dict[str, str] = {
    "ceit": "ceit",
    "ep": "ep",
    "ec": "ec",
    "arch": "arch",
    "archi": "arch",
    "architecture": "arch",
    "mc": "mc",
    "mech": "mech",
    "me": "mech",
    "mechanical": "mech",
    "civil": "civil",
}

MAJOR_NAMES: dict[str, str] = {
    "ceit": "CEIT",
    "ep": "EP",
    "ec": "EC",
    "arch": "Architecture",
    "mc": "MC",
    "mech": "Mechanical",
    "civil": "Civil",
}

MAJOR_DB_SLUGS: dict[str, list[str]] = {
    "ceit": ["ceit"],
    "ep": ["ep"],
    "ec": ["ec"],
    "arch": ["arch", "archi"],
    "mc": ["mc"],
    "mech": ["mech", "me"],
    "civil": ["civil"],
}


def normalize_major_slug(value: Optional[str]) -> Optional[str]:
    """Normalize major slug or name to canonical Mini App slug (e.g. archi -> arch, me -> mech)."""
    if not value or not str(value).strip():
        return None
    cleaned = str(value).strip().lower()
    return MAJOR_CANONICAL_SLUGS.get(cleaned, cleaned)


def get_major_name(value: Optional[str]) -> Optional[str]:
    """Return official major display name for a given slug or alias."""
    canon = normalize_major_slug(value)
    if not canon:
        return None
    return MAJOR_NAMES.get(canon)


def build_major_filter(major_param: Optional[str]) -> dict:
    """Build a MongoDB query fragment for major filtering.

    Handles legacy and bot identifiers (e.g. 'archi' for Architecture, 'me' for Mechanical)
    as well as canonical values, ensuring complete compatibility across Bot and Mini App.
    """
    if not major_param or major_param == "all":
        return {}

    cleaned = str(major_param).strip().lower()
    if not cleaned:
        return {}

    canon = MAJOR_CANONICAL_SLUGS.get(cleaned)
    if canon:
        db_slugs = MAJOR_DB_SLUGS.get(canon, [canon])
        major_name = MAJOR_NAMES.get(canon)
        return {
            "$or": [
                {"major_slug": {"$in": db_slugs}},
                {"major": major_name},
            ]
        }

    # Fallback for unrecognized identifiers
    return {
        "$or": [
            {"major_slug": cleaned},
            {"major": major_param.strip()},
        ]
    }
