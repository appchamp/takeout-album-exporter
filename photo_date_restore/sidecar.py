"""Media <-> Google Takeout JSON sidecar matching (reverse index from the JSON side).

Pure functions only — no filesystem I/O beyond what the caller already read.
Design reference: docs/design.md §5.

Algorithm summary
------------------
For each candidate JSON sidecar in a directory we compute:
  - stem: the JSON filename with a trailing dup marker "(n)" and a
    (possibly truncated) ".supplemental-metadata" suffix removed.
  - dup: the "(n)" duplicate index, if present.
  - title: the sidecar's own "title" field (already NFC-normalized).

For each media filename we then test, in descending trust order:
  T1 EXACT_TITLE        NFC(title) == NFC(basename) [dup-marker tolerant]
  T2 EXACT_NAME         stem (with dup re-inserted) == basename, case-sensitive
  T3 DERIVED_VERIFIED   edited-suffix/extension-less/casefold transform of the
                         media name matches the stem AND the title corroborates it
  T4 TRUNCATED_PREFIX   stem is a long (>=20 char) prefix of basename AND title
                         matches exactly (covers Google's 51-char filename cap)

If a media file's best tier has more than one candidate JSON, or a JSON ends up
being the best pick of more than one media file, the outcome is AMBIGUOUS_JSON.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import JsonMatchTier

SUPPLEMENTAL_SUFFIX = "supplemental-metadata"

EDIT_SUFFIXES = [
    "-edited", "-編集済み", "-bearbeitet", "-bewerkt", "-edytowane",
    "-modificato", "-modifié", "-modifie", "-ha editado", "-editat",
    "-effects", "-smile", "-mix",
]

_DUP_RE = re.compile(r"\((\d+)\)$")

# Tier ranking: lower number = stronger trust.
_TIER_ORDER = {
    JsonMatchTier.T1_EXACT_TITLE: 1,
    JsonMatchTier.T2_EXACT_NAME: 2,
    JsonMatchTier.T3_DERIVED_VERIFIED: 3,
    JsonMatchTier.T4_TRUNCATED_PREFIX: 4,
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def strip_dup_marker(name: str) -> str:
    """Remove a trailing "(n)" immediately before the extension, if present."""
    root, ext = os.path.splitext(name)
    m = _DUP_RE.search(root)
    if m:
        root = root[: m.start()]
    return root + ext


@dataclass(frozen=True)
class JsonCandidate:
    """Parsed identity of one sidecar JSON, ready for matching."""

    ref: object  # opaque token the caller uses to identify this JSON (e.g. path)
    stem: str
    dup: Optional[int]
    title: Optional[str]
    truncated: bool


def parse_json_filename(filename: str) -> tuple[str, Optional[int], bool]:
    """Split a sidecar filename into (stem, dup, truncated).

    `filename` must end with ".json". `stem` is the best-effort original media
    filename (including its extension) with the dup marker and supplemental
    suffix removed.
    """
    if not filename.endswith(".json"):
        raise ValueError(f"not a .json filename: {filename}")
    base = filename[: -len(".json")]

    dup: Optional[int] = None
    m = _DUP_RE.search(base)
    if m:
        dup = int(m.group(1))
        base = base[: m.start()]

    truncated = False
    for length in range(len(SUPPLEMENTAL_SUFFIX), 0, -1):
        suffix = "." + SUPPLEMENTAL_SUFFIX[:length]
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            truncated = length < len(SUPPLEMENTAL_SUFFIX)
            break

    return base, dup, truncated


def make_candidate(ref: object, filename: str, title: Optional[str]) -> JsonCandidate:
    stem, dup, truncated = parse_json_filename(filename)
    return JsonCandidate(ref=ref, stem=stem, dup=dup, title=nfc(title) if title else None, truncated=truncated)


def _candidate_media_names(cand: JsonCandidate) -> List[str]:
    names = [cand.stem]
    if cand.dup is not None:
        root, ext = os.path.splitext(cand.stem)
        names.append(f"{root}({cand.dup}){ext}")
    return names


def _apply_edit_suffixes(name: str) -> List[str]:
    root, ext = os.path.splitext(name)
    out = [name]
    for suffix in EDIT_SUFFIXES:
        if root.endswith(suffix):
            out.append(root[: -len(suffix)] + ext)
    return out


def _extensionless_variant(name: str) -> str:
    root, _ext = os.path.splitext(name)
    return root


def _tier_for(media_name: str, cand: JsonCandidate) -> Optional[JsonMatchTier]:
    """Return the best tier at which `cand` matches `media_name`, or None."""
    media_nfc = nfc(media_name)
    media_nodup_nfc = nfc(strip_dup_marker(media_name))

    # T1: title match (dup-marker tolerant, per GPTH #59: title omits "(n)").
    if cand.title is not None and cand.title in (media_nfc, media_nodup_nfc):
        return JsonMatchTier.T1_EXACT_TITLE

    candidate_names = _candidate_media_names(cand)

    # T2: exact stem/name match, case-sensitive.
    if media_name in candidate_names:
        return JsonMatchTier.T2_EXACT_NAME

    # T3: derived transforms (edited-suffix removal, extensionless, casefold),
    # corroborated by title when available. The title is expected to match
    # whichever transformed form of the media name actually lined up with the
    # JSON's stem (e.g. an "-edited" copy shares its original's JSON/title).
    media_variants = set(_apply_edit_suffixes(media_name))
    media_variants.add(_extensionless_variant(media_name))
    media_variants.add(media_name)
    derived_hit = False
    for cname in candidate_names:
        if cname in media_variants or cname.casefold() == media_name.casefold():
            derived_hit = True
            break
    if derived_hit:
        title_pool = {nfc(v).casefold() for v in media_variants}
        title_pool.add(media_nfc.casefold())
        title_pool.add(media_nodup_nfc.casefold())
        if cand.title is None or cand.title.casefold() in title_pool:
            return JsonMatchTier.T3_DERIVED_VERIFIED

    # T4: truncated stem is a long prefix of the media name, backed by title.
    if cand.truncated and len(cand.stem) >= 20 and media_name.startswith(cand.stem):
        if cand.title is not None and cand.title in (media_nfc, media_nodup_nfc):
            return JsonMatchTier.T4_TRUNCATED_PREFIX

    return None


@dataclass
class MatchOutcome:
    tier: JsonMatchTier
    sidecar_ref: Optional[object]
    candidate_count: int
    candidate_refs: List[object] = field(default_factory=list)


def match_all(media_names: List[str], candidates: List[JsonCandidate]) -> Dict[str, MatchOutcome]:
    """Match every media filename against the JSON candidates in its directory.

    Returns a dict media_name -> MatchOutcome. `sidecar_ref` is None when the
    outcome is NO_JSON or AMBIGUOUS_JSON; `candidate_count` records how many
    JSONs tied at the best tier found (0 = no match at all).
    """
    # Step 1: for every media, collect (tier, cand) pairs across all candidates.
    per_media: Dict[str, List[tuple[JsonMatchTier, JsonCandidate]]] = {}
    for media in media_names:
        hits = []
        for cand in candidates:
            tier = _tier_for(media, cand)
            if tier is not None:
                hits.append((tier, cand))
        per_media[media] = hits

    # Step 2: pick the best (lowest tier order) per media.
    best_choice: Dict[str, tuple[JsonMatchTier, List[JsonCandidate]]] = {}
    for media, hits in per_media.items():
        if not hits:
            best_choice[media] = (JsonMatchTier.NONE, [])
            continue
        best_order = min(_TIER_ORDER[t] for t, _ in hits)
        best_tier = [t for t in _TIER_ORDER if _TIER_ORDER[t] == best_order][0]
        best_cands = [c for t, c in hits if t == best_tier]
        best_choice[media] = (best_tier, best_cands)

    # Step 3: enforce the 1:1 constraint — a JSON claimed as the top pick by
    # more than one media becomes AMBIGUOUS for all claimants (design §5.4-4).
    claim_count: Dict[object, int] = {}
    for media, (tier, cands) in best_choice.items():
        if tier != JsonMatchTier.NONE and len(cands) == 1:
            ref = cands[0].ref
            claim_count[ref] = claim_count.get(ref, 0) + 1

    results: Dict[str, MatchOutcome] = {}
    for media, (tier, cands) in best_choice.items():
        cand_refs = [c.ref for c in cands]
        if tier == JsonMatchTier.NONE:
            results[media] = MatchOutcome(tier=JsonMatchTier.NONE, sidecar_ref=None, candidate_count=0, candidate_refs=[])
            continue
        if len(cands) > 1:
            results[media] = MatchOutcome(tier=tier, sidecar_ref=None, candidate_count=len(cands), candidate_refs=cand_refs)
            continue
        ref = cands[0].ref
        if claim_count.get(ref, 0) > 1:
            results[media] = MatchOutcome(tier=tier, sidecar_ref=None, candidate_count=claim_count[ref], candidate_refs=[ref])
            continue
        results[media] = MatchOutcome(tier=tier, sidecar_ref=ref, candidate_count=1, candidate_refs=[ref])

    return results
