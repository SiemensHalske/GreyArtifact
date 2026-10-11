from __future__ import annotations

from app.services.parsers import ParserError, canonical_domain


def target_snapshot(targets) -> list[dict]:
    normalized = []
    seen = set()
    for target in targets:
        domain = canonical_domain(target["domain"])
        item = (domain, bool(target.get("include_subdomains", True)))
        if item in seen:
            continue
        seen.add(item)
        normalized.append(
            {"domain": domain, "include_subdomains": item[1]}
        )
    return sorted(normalized, key=lambda value: (value["domain"], value["include_subdomains"]))


def domain_matches_target(domain: str, target: dict) -> bool:
    expected = target["domain"]
    return domain == expected or (
        target.get("include_subdomains", True) and domain.endswith(f".{expected}")
    )


def domain_is_authorized(domain: str, snapshot: dict) -> bool:
    try:
        normalized = canonical_domain(domain)
    except ParserError:
        return False
    allowed = any(
        domain_matches_target(normalized, target)
        for target in snapshot.get("allowed_targets", [])
    )
    excluded = any(
        domain_matches_target(normalized, target)
        for target in snapshot.get("excluded_targets", [])
    )
    return allowed and not excluded
