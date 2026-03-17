MODE_LOOKUP = {
    "personalgrowth": "personal_growth",
    "personal_growth": "personal_growth",
    "personal": "personal_growth",
    "betterme": "personal_growth",
    "better_me": "personal_growth",
    "coaching": "coaching",
    "relationship": "relationship_private",
    "relationshipshared": "relationship_private",
    "relationshipprivate": "relationship_private",
    "relationship_private": "relationship_private",
    "private": "relationship_private",
    "betterus": "relationship_private",
    "better_us": "relationship_private",
    "mediation": "relationship_medication",
    "relationshipmediation": "relationship_medication",
    "relationship_mediation": "relationship_medication",
    "relationshipmedication": "relationship_medication",
    "relationship_medication": "relationship_medication",
}


def normalize_mode(raw_mode: str) -> str:
    key = (raw_mode or "").replace(" ", "").replace("-", "_").lower()
    return MODE_LOOKUP.get(key, key)
