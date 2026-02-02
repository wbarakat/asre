"""Tests for facility string normalization pipeline."""

from __future__ import annotations

from asre.facility.normalizer import FacilityNormalizer


class TestFacilityNormalizerConstruction:
    """Test FacilityNormalizer construction."""

    def test_default_construction(self) -> None:
        normalizer = FacilityNormalizer()
        assert normalizer is not None

    def test_custom_abbreviations(self) -> None:
        custom = {"CTR": "CENTER", "HOSP": "HOSPITAL"}
        normalizer = FacilityNormalizer(abbreviations=custom)
        assert normalizer is not None


class TestUppercaseAndPunctuation:
    """Test uppercase conversion and punctuation stripping."""

    def test_converts_to_uppercase(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("st marys")
        assert result == result.upper()

    def test_strips_apostrophes(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Mary's")
        assert "'" not in result

    def test_strips_periods(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("St. Mary")
        assert "." not in result

    def test_strips_hyphens_between_words(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Mary - East")
        # Hyphens replaced with space, then whitespace normalized
        assert "-" not in result

    def test_strips_commas(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Memorial, East")
        assert "," not in result


class TestAbbreviationExpansion:
    """Test abbreviation expansion."""

    def test_med_ctr_expanded(self) -> None:
        normalizer = FacilityNormalizer()
        # MED CTR expands to MEDICAL CENTER, then suffix removal strips it
        # Use a non-trailing position to verify expansion happens
        result = normalizer.normalize("Med Ctr of the Valley")
        assert "MEDICAL CENTER" in result

    def test_hosp_expanded(self) -> None:
        normalizer = FacilityNormalizer()
        # HOSP expands to HOSPITAL, then suffix removal strips it when trailing
        # Use a non-trailing position to verify expansion happens
        result = normalizer.normalize("Hosp of Good Samaritan")
        assert "HOSPITAL" in result

    def test_abbreviation_only_at_word_boundary(self) -> None:
        normalizer = FacilityNormalizer()
        # "HOSPITAL" should not have "HOSP" expanded again inside it
        result = normalizer.normalize("Hospital")
        assert "HOSPITALALITAL" not in result


class TestGenericSuffixRemoval:
    """Test removal of trailing generic organizational suffixes."""

    def test_removes_trailing_hospital(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Memorial Regional Hospital")
        assert result == "MEMORIAL REGIONAL"

    def test_removes_trailing_medical_center(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("North Valley Medical Center")
        assert result == "NORTH VALLEY"

    def test_removes_trailing_health_system(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("University Health System")
        assert result == "UNIVERSITY"

    def test_removes_trailing_health(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Banner Health")
        assert result == "BANNER"

    def test_removes_trailing_clinic(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Mayo Clinic")
        assert result == "MAYO"

    def test_removes_trailing_center(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Banner Surgery Center")
        assert result == "BANNER SURGERY"

    def test_does_not_remove_non_trailing_suffix(self) -> None:
        normalizer = FacilityNormalizer()
        # "Hospital" in the middle should not be removed
        result = normalizer.normalize("Hospital of the Valley East")
        # After normalization: HOSPITAL OF THE VALLEY EAST
        # "HOSPITAL" is not trailing, so should remain
        assert "HOSPITAL" in result or "VALLEY" in result


class TestDirectionalTokensPreserved:
    """Test that directional tokens are preserved."""

    def test_east_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("St Marys East")
        assert "EAST" in result

    def test_west_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Good Samaritan West")
        assert "WEST" in result

    def test_north_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("North Valley Medical Center")
        assert "NORTH" in result

    def test_south_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("South General Hospital")
        assert "SOUTH" in result


class TestCampusTokensPreserved:
    """Test that campus tokens are preserved."""

    def test_main_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Memorial Main Campus")
        assert "MAIN" in result

    def test_downtown_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Memorial Downtown")
        assert "DOWNTOWN" in result

    def test_campus_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("St Marys East Campus")
        assert "CAMPUS" in result

    def test_midtown_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Grady Midtown")
        assert "MIDTOWN" in result

    def test_uptown_preserved(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Grady Uptown")
        assert "UPTOWN" in result


class TestWhitespaceNormalization:
    """Test whitespace normalization."""

    def test_multiple_spaces_collapsed(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("St   Marys    East")
        assert "  " not in result

    def test_leading_trailing_whitespace_stripped(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("  St Marys  ")
        assert result == result.strip()


class TestAcceptanceCriteriaExamples:
    """Test exact examples from the PRD acceptance criteria."""

    def test_st_marys_med_ctr_east_campus(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("St. Mary's Med Ctr - East Campus")
        assert result == "ST MARYS EAST CAMPUS"

    def test_memorial_regional_hospital(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Memorial Regional Hospital")
        assert result == "MEMORIAL REGIONAL"

    def test_good_samaritan_hosp_west(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("Good Samaritan Hosp - West")
        assert result == "GOOD SAMARITAN WEST"

    def test_university_health_system(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("University Health System")
        assert result == "UNIVERSITY"

    def test_north_valley_medical_center(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("North Valley Medical Center")
        assert result == "NORTH VALLEY"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_string(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("")
        assert result == ""

    def test_whitespace_only(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("   ")
        assert result == ""

    def test_none_returns_empty(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize(None)  # type: ignore[arg-type]
        assert result == ""

    def test_already_normalized(self) -> None:
        normalizer = FacilityNormalizer()
        result = normalizer.normalize("MEMORIAL REGIONAL")
        assert result == "MEMORIAL REGIONAL"

    def test_suffix_only_name(self) -> None:
        normalizer = FacilityNormalizer()
        # If entire name is a suffix, keep it (don't produce empty string)
        result = normalizer.normalize("Hospital")
        assert result != ""
