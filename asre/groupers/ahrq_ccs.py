"""AHRQ CCS grouper — ICD-10-CM to episode type classification (US-092).

Uses AHRQ Clinical Classifications Software (CCS) ICD-10 categories
to map diagnosis codes to episode type classifications. DRG-based rules
are checked first, then ICD-10 codes are classified via CCS category
prefix matching.
"""

from __future__ import annotations

from asre.groupers.base import ConditionGrouper

# ---------------------------------------------------------------------------
# DRG-based surgical ranges (MS-DRG)
# ---------------------------------------------------------------------------
_SURGICAL_DRG_RANGES: list[tuple[int, int]] = [
    (1, 42),       # Nervous system OR procedures
    (113, 117),    # Orbital procedures
    (129, 139),    # Major head & neck procedures
    (163, 168),    # Major chest procedures
    (215, 245),    # Cardiac surgery (incl. CABG 231-236, valve 216-221)
    (246, 267),    # Vascular procedures
    (326, 358),    # Stomach/esophageal/digestive OR procedures
    (405, 425),    # Hepatobiliary & pancreas OR procedures
    (453, 520),    # Musculoskeletal OR procedures (incl. hip/knee 469-470, 480-482)
    (570, 585),    # Skin/breast OR procedures
    (614, 630),    # Adrenal & pituitary procedures
    (652, 675),    # Kidney & urinary tract OR procedures
    (707, 718),    # Male reproductive OR procedures
    (734, 750),    # Female reproductive OR procedures
    (799, 804),    # Splenectomy
    (820, 830),    # Lymphoma & leukemia OR procedures
    (901, 909),    # Wound debridement / skin graft
    (955, 959),    # Craniotomy for trauma
    (969, 970),    # HIV w/ OR procedure
]

_MATERNITY_DRG_RANGES: list[tuple[int, int]] = [
    (765, 768),    # Cesarean section
    (774, 775),    # Vaginal delivery w/ complications
    (796, 798),    # Vaginal delivery
]

_BEHAVIORAL_HEALTH_DRG_RANGES: list[tuple[int, int]] = [
    (876, 887),    # Mental illness / psychoses
    (894, 897),    # Alcohol/drug abuse
]

# ---------------------------------------------------------------------------
# ICD-10-CM prefix -> episode type mapping (AHRQ CCS-based)
#
# These prefixes map ICD-10 chapters and clinical groupings to episode types.
# Ordered from most specific to least specific for correct matching.
# ---------------------------------------------------------------------------

# Chronic exacerbation conditions (CCS categories for chronic disease
# exacerbations — heart failure, COPD, asthma, diabetes complications, CKD)
_CHRONIC_EXACERBATION_PREFIXES: list[str] = [
    "I50",    # Heart failure
    "J44",    # COPD
    "J45",    # Asthma
    "J96",    # Respiratory failure
    "E10",    # Type 1 diabetes with complications
    "E11",    # Type 2 diabetes with complications
    "E13",    # Other diabetes with complications
    "N17",    # Acute kidney failure
    "N18",    # Chronic kidney disease
    "I48",    # Atrial fibrillation (recurrent)
    "J47",    # Bronchiectasis
    "J84",    # Interstitial pulmonary disease
    "K70",    # Alcoholic liver disease
    "K74",    # Fibrosis / cirrhosis of liver
]

# Maternity conditions (O00-O9A chapter)
_MATERNITY_PREFIXES: list[str] = [
    "O",      # Pregnancy, childbirth, and puerperium (entire chapter)
    "Z37",    # Outcome of delivery
]

# Behavioral health conditions (F01-F99 chapter)
_BEHAVIORAL_HEALTH_PREFIXES: list[str] = [
    "F",      # Mental, behavioral, neurodevelopmental disorders (entire chapter)
]

# Surgical/procedure-related ICD-10 codes (injuries commonly requiring surgery)
_SURGICAL_PREFIXES: list[str] = [
    "S72",    # Fracture of femur (hip fracture)
    "S82",    # Fracture of lower leg
    "S42",    # Fracture of shoulder / upper arm
    "T84",    # Complications of internal orthopedic devices
    "M17",    # Gonarthrosis (knee OA — joint replacement)
    "M16",    # Coxarthrosis (hip OA — joint replacement)
]

# Medical conditions — broad ICD-10 categories that are medical (non-surgical,
# non-chronic-exacerbation). These are checked last as a catch-all before
# unclassified. Using chapter-level prefixes.
_MEDICAL_CHAPTER_PREFIXES: list[str] = [
    "A", "B",   # Infectious diseases
    "C", "D0", "D1", "D2", "D3", "D4",  # Neoplasms
    "D5", "D6", "D7", "D8", "D9",  # Blood/immune
    "E",         # Endocrine/metabolic (non-chronic subcodes handled above)
    "G",         # Nervous system
    "H",         # Eye / ear
    "I",         # Circulatory (non-chronic subcodes handled above)
    "J",         # Respiratory (non-chronic subcodes handled above)
    "K",         # Digestive
    "L",         # Skin
    "M",         # Musculoskeletal (non-surgical subcodes)
    "N",         # Genitourinary (non-chronic subcodes handled above)
    "R",         # Symptoms/signs
    "S", "T",    # Injury (non-surgical subcodes)
    "Z",         # Factors influencing health
]


def _drg_in_ranges(drg_int: int, ranges: list[tuple[int, int]]) -> bool:
    """Check if a DRG integer falls within any of the given inclusive ranges."""
    for lo, hi in ranges:
        if lo <= drg_int <= hi:
            return True
    return False


def _match_prefix(code: str, prefixes: list[str]) -> bool:
    """Check if an ICD-10 code starts with any of the given prefixes."""
    code_upper = code.upper().replace(".", "")
    for prefix in prefixes:
        if code_upper.startswith(prefix):
            return True
    return False


class AHRQCCSGrouper(ConditionGrouper):
    """AHRQ CCS-based condition grouper.

    Classifies episodes using:
    1. DRG-based rules (checked first, highest priority)
    2. ICD-10-CM prefix matching against AHRQ CCS category groupings
    """

    def group(
        self,
        diagnosis_codes: list[dict[str, str | None]],
        drg: str | None,
    ) -> str:
        """Classify an episode based on DRG and/or ICD-10 diagnosis codes.

        DRG rules are evaluated first. If no DRG match, the principal
        (first) diagnosis code is classified via ICD-10 prefix matching.
        """
        # --- DRG-based classification (highest priority) ---
        if drg is not None:
            drg_result = self._classify_by_drg(drg)
            if drg_result is not None:
                return drg_result

        # --- ICD-10 based classification (AHRQ CCS fallback) ---
        if diagnosis_codes:
            return self._classify_by_icd10(diagnosis_codes)

        return "unclassified"

    def _classify_by_drg(self, drg: str) -> str | None:
        """Classify by MS-DRG code. Returns None if DRG not recognized."""
        try:
            drg_int = int(drg)
        except (ValueError, TypeError):
            return None

        if _drg_in_ranges(drg_int, _SURGICAL_DRG_RANGES):
            return "surgical"
        if _drg_in_ranges(drg_int, _MATERNITY_DRG_RANGES):
            return "maternity"
        if _drg_in_ranges(drg_int, _BEHAVIORAL_HEALTH_DRG_RANGES):
            return "behavioral_health"

        return None

    def _classify_by_icd10(
        self, diagnosis_codes: list[dict[str, str | None]]
    ) -> str:
        """Classify by principal ICD-10 code using CCS category mappings.

        Uses the first diagnosis code (principal diagnosis) for classification.
        Checks more specific categories (chronic exacerbation, maternity,
        behavioral health, surgical) before the broad medical catch-all.
        """
        principal = diagnosis_codes[0]
        code = principal.get("code")
        if code is None:
            return "unclassified"

        # Check specific categories first (order matters)
        if _match_prefix(code, _CHRONIC_EXACERBATION_PREFIXES):
            return "chronic_exacerbation"
        if _match_prefix(code, _MATERNITY_PREFIXES):
            return "maternity"
        if _match_prefix(code, _BEHAVIORAL_HEALTH_PREFIXES):
            return "behavioral_health"
        if _match_prefix(code, _SURGICAL_PREFIXES):
            return "surgical"
        if _match_prefix(code, _MEDICAL_CHAPTER_PREFIXES):
            return "medical"

        return "unclassified"
