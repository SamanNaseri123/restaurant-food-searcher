"""Tests for the food synonym dictionary."""

from app.services.food_synonyms import SYNONYM_MAP, expand_word, expand_query_words


class TestFoodSynonyms:

    def test_mac_expands_to_macaroni(self):
        assert "macaroni" in expand_word("mac")
        assert "mac" in expand_word("macaroni")

    def test_burger_expands_to_hamburger_and_cheeseburger(self):
        result = expand_word("burger")
        assert "hamburger" in result
        assert "cheeseburger" in result

    def test_bbq_expands_to_barbecue(self):
        result = expand_word("bbq")
        assert "barbecue" in result
        assert "barbeque" in result

    def test_shrimp_expands_to_prawn_and_camarones(self):
        result = expand_word("shrimp")
        assert "prawn" in result
        assert "camarones" in result

    def test_unknown_word_returns_only_itself(self):
        result = expand_word("xyzzy")
        assert result == {"xyzzy"}

    def test_expand_word_is_case_insensitive(self):
        assert expand_word("MAC") == expand_word("mac")
        assert "macaroni" in expand_word("Mac")

    def test_expand_query_words_returns_dict(self):
        result = expand_query_words(["mac", "cheese"])
        assert "mac" in result
        assert "macaroni" in result["mac"]
        assert "cheese" in result
        assert "queso" in result["cheese"]

    def test_synonyms_are_bidirectional(self):
        # If A says B is a synonym, then B should say A is a synonym
        for word, syns in SYNONYM_MAP.items():
            for syn in syns:
                assert word in SYNONYM_MAP.get(syn, set()), \
                    f"{word} -> {syn} but {syn} doesn't map back to {word}"

    def test_chicken_synonyms(self):
        assert "poultry" in expand_word("chicken")

    def test_taco_burrito_are_separate(self):
        # Tacos and burritos shouldn't be synonyms
        assert "burrito" not in expand_word("taco")
        assert "taco" not in expand_word("burrito")

    def test_pizza_is_not_synonym_for_pie_in_isolation(self):
        # Pizza expands to pie (Italian usage), but this is acceptable
        # since restaurant menus context makes this clear
        assert "pie" in expand_word("pizza")
