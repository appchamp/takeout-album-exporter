"""Unit tests for photo_date_restore.sidecar (JSON matching, §21.2 of docs/design.md)."""
import unicodedata

from photo_date_restore.models import JsonMatchTier
from photo_date_restore.sidecar import make_candidate, match_all


def cand(ref, filename, title):
    return make_candidate(ref, filename, title)


def test_exact_json_suffix():
    c = cand("j1", "IMG.JPG.json", "IMG.JPG")
    result = match_all(["IMG.JPG"], [c])
    assert result["IMG.JPG"].tier == JsonMatchTier.T1_EXACT_TITLE
    assert result["IMG.JPG"].sidecar_ref == "j1"


def test_supplemental_metadata_suffix():
    c = cand("j1", "IMG_0001.JPG.supplemental-metadata.json", "IMG_0001.JPG")
    result = match_all(["IMG_0001.JPG"], [c])
    assert result["IMG_0001.JPG"].sidecar_ref == "j1"
    assert result["IMG_0001.JPG"].tier == JsonMatchTier.T1_EXACT_TITLE


def test_truncated_supplemental_metadata_suffix():
    long_name = "Urlaub-in-den-bergen-mit-familie-und-freunden-2019(38).JPG"
    # Google's 51-char cap truncates "supplemental-metadata" progressively.
    json_name = long_name + ".supplemental-metada.json"
    c = cand("j1", json_name, long_name)
    result = match_all([long_name], [c])
    assert result[long_name].sidecar_ref == "j1"
    assert result[long_name].tier == JsonMatchTier.T1_EXACT_TITLE


def test_duplicate_suffix_bracket_swap():
    # GPTH #59: image(11).jpg <-> image.jpg(11).json, title lacks the "(n)".
    c = cand("j1", "image.jpg(11).json", "image.jpg")
    result = match_all(["image(11).jpg"], [c])
    assert result["image(11).jpg"].sidecar_ref == "j1"
    assert result["image(11).jpg"].tier == JsonMatchTier.T1_EXACT_TITLE


def test_duplicate_and_original_coexist_1to1():
    c_orig = cand("j_orig", "IMG_4081.JPG.json", "IMG_4081.JPG")
    c_dup = cand("j_dup", "IMG_4081.JPG(1).json", "IMG_4081.JPG")
    result = match_all(["IMG_4081.jpg", "IMG_4081(1).jpg"], [c_orig, c_dup])
    # Original matches by exact-name (T2, case-sensitive fails due to case
    # difference so falls through to casefold-based T3), duplicate by dup-swap.
    assert result["IMG_4081(1).jpg"].sidecar_ref == "j_dup"


def test_edited_suffix_variant():
    c = cand("j1", "IMG_1.jpg.json", "IMG_1.jpg")
    result = match_all(["IMG_1-edited.jpg"], [c])
    assert result["IMG_1-edited.jpg"].sidecar_ref == "j1"
    assert result["IMG_1-edited.jpg"].tier == JsonMatchTier.T3_DERIVED_VERIFIED


def test_nfd_filename_vs_nfc_title():
    nfc_name = unicodedata.normalize("NFC", "が.jpg")
    nfd_name = unicodedata.normalize("NFD", "が.jpg")
    assert nfc_name != nfd_name  # sanity: they really are different byte sequences
    c = cand("j1", nfc_name + ".json", nfc_name)
    result = match_all([nfd_name], [c])
    assert result[nfd_name].sidecar_ref == "j1"


def test_casefold_fallback_downgrades_tier():
    c = cand("j1", "IMG.JPG.json", "IMG.JPG")
    result = match_all(["img.jpg"], [c])
    assert result["img.jpg"].sidecar_ref == "j1"
    assert result["img.jpg"].tier == JsonMatchTier.T3_DERIVED_VERIFIED


def test_no_json_candidates():
    result = match_all(["orphan.jpg"], [])
    assert result["orphan.jpg"].sidecar_ref is None
    assert result["orphan.jpg"].tier == JsonMatchTier.NONE


def test_ambiguous_two_jsons_same_media():
    c1 = cand("j1", "IMG.jpg.json", "IMG.jpg")
    c2 = cand("j2", "IMG.jpg.supplemental-metadata.json", "IMG.jpg")
    result = match_all(["IMG.jpg"], [c1, c2])
    assert result["IMG.jpg"].sidecar_ref is None
    assert result["IMG.jpg"].candidate_count == 2


def test_ambiguous_one_json_claimed_by_two_media():
    # design §5.4-4: if the same JSON is the sole top candidate for more than
    # one media file, BOTH are pushed back to AMBIGUOUS (1:1 constraint).
    c = cand("j1", "IMG.jpg.json", "IMG.jpg")
    result = match_all(["IMG.jpg", "img.jpg"], [c])
    assert result["IMG.jpg"].sidecar_ref is None
    assert result["img.jpg"].sidecar_ref is None


def test_extensionless_media():
    c = cand("j1", "20030616.json", "20030616")
    result = match_all(["20030616"], [c])
    assert result["20030616"].sidecar_ref == "j1"


def test_extension_case_mismatch_title():
    c = cand("j1", "IMG.JPG.json", "IMG.JPG")
    result = match_all(["img.jpg"], [c])
    assert result["img.jpg"].sidecar_ref == "j1"
    assert result["img.jpg"].tier == JsonMatchTier.T3_DERIVED_VERIFIED
