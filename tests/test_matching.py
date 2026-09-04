from elk_lead_agent import matching


def test_find_categories_basic(config):
    keys, labels = matching.find_categories("Neues Budgethotel in Wien", config)
    assert "budget_hotels" in keys
    assert "Budget-Hotels" in labels


def test_find_categories_multiple(config):
    text = "Apartmenthotel mit Mitarbeiterunterkunft"
    keys, _ = matching.find_categories(text, config)
    assert "serviced_apartments" in keys
    assert "mitarbeiterquartiere" in keys


def test_umlaut_plural_matches(config):
    # Plural with umlaut must still be recognized (real-world text).
    keys, _ = matching.find_categories("Modulbau-Arbeiterunterkünfte für Bund", config)
    assert "arbeiterunterkuenfte" in keys


def test_case_insensitive(config):
    assert matching.matched_terms("STUDENTENWOHNHEIM", ["Studentenwohnheim"])


def test_timber_detection(config):
    assert matching.mentions_timber_or_modular("in Holzhybridbauweise", config)
    assert not matching.mentions_timber_or_modular("Stahlbetonbau", config)


def test_submission_detection(config):
    assert matching.submission_imminent("Einreichung steht bevor", config)
    assert matching.submission_imminent("Bauverhandlung angesetzt", config)
    assert not matching.submission_imminent("nur eine Projektidee", config)
