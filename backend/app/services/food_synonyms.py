"""Food synonym dictionary for menu search.

Hand-curated based on actual menu data in the database. Each key is a word
that, when searched, should also match items containing any of its synonyms.

Synonyms are bidirectional — if "mac" -> "macaroni", then "macaroni" -> "mac".

Used by SearchService to expand query words at search time.
"""

# Each entry is a set of words that all refer to the same thing.
# Order doesn't matter — we build a bidirectional lookup at module load.
_SYNONYM_GROUPS: list[set[str]] = [
    # Pasta / mac & cheese
    {"mac", "macaroni"},
    {"spaghetti", "pasta", "noodles", "noodle"},
    {"ravioli", "raviolo"},
    {"lasagna", "lasagne"},

    # BBQ
    {"bbq", "barbecue", "barbeque", "bar-b-q"},

    # Burgers
    {"burger", "hamburger", "cheeseburger"},
    {"slider", "sliders"},

    # Chicken cuts
    {"chicken", "poultry"},
    {"wings", "wing"},
    {"tenders", "tender", "strips", "fingers"},
    {"breast", "breasts"},
    {"thigh", "thighs"},

    # Beef
    {"beef", "steak", "carne", "cow"},
    {"ribeye", "rib-eye", "rib eye"},
    {"sirloin", "tri-tip", "tritip"},
    {"filet", "filet mignon", "tenderloin"},
    {"brisket", "smoked brisket"},
    {"meatball", "meatballs", "albondigas"},

    # Pork
    {"pork", "chorizo", "carnitas"},
    {"bacon", "pancetta"},
    {"ham", "jamon"},
    {"sausage", "sausages", "chorizo", "linguica"},

    # Seafood
    {"shrimp", "prawn", "prawns", "camarones"},
    {"fish", "pescado"},
    {"salmon", "lox"},
    {"tuna", "ahi"},
    {"crab", "krab", "crabmeat"},
    {"lobster", "langosta"},
    {"calamari", "squid", "calamares"},
    {"scallop", "scallops"},
    {"octopus", "pulpo"},
    {"clam", "clams", "almejas"},
    {"oyster", "oysters", "ostiones"},
    {"cod", "bacalao"},
    {"mahi", "mahi-mahi", "dorado"},

    # Vegetables
    {"avocado", "guac", "guacamole"},
    {"tomato", "tomatoes", "jitomate"},
    {"onion", "onions", "cebolla"},
    {"pepper", "peppers", "chile", "chiles", "chili", "chilies", "chiles"},
    {"jalapeno", "jalapeño", "jalapenos"},
    {"mushroom", "mushrooms", "shrooms", "champignon", "champignons"},
    {"eggplant", "aubergine", "berenjena"},
    {"corn", "elote", "maize"},
    {"cilantro", "coriander"},
    {"lettuce", "greens"},
    {"spinach", "espinaca"},
    {"broccoli", "broccolini"},
    {"cabbage", "col"},
    {"potato", "potatoes", "papa", "papas"},
    {"bean", "beans", "frijol", "frijoles"},
    {"rice", "arroz"},

    # Cheese
    {"cheese", "queso"},
    {"mozzarella", "mozz"},
    {"cheddar", "cheddar cheese"},
    {"parmesan", "parm", "parmigiano"},
    {"feta", "feta cheese"},
    {"cotija", "cotija cheese"},

    # Mexican
    {"taco", "tacos"},
    {"burrito", "burritos"},
    {"quesadilla", "quesadillas"},
    {"enchilada", "enchiladas"},
    {"tostada", "tostadas"},
    {"torta", "tortas"},
    {"chimichanga", "chimichangas"},
    {"tamale", "tamales"},
    {"empanada", "empanadas"},
    {"sope", "sopes"},
    {"flauta", "flautas", "taquito", "taquitos"},
    {"tortilla", "tortillas"},
    {"salsa", "sauce", "dip"},
    {"pico", "pico de gallo"},
    {"asada", "carne asada"},
    {"al pastor", "pastor"},

    # Asian / sushi
    {"sushi", "nigiri", "sashimi"},
    {"roll", "rolls", "maki"},
    {"ramen", "noodle soup"},
    {"pho", "pho noodle soup"},
    {"udon", "udon noodles"},
    {"soba", "soba noodles"},
    {"tempura", "tempura battered"},
    {"teriyaki", "teri"},
    {"katsu", "tonkatsu"},
    {"gyoza", "potstickers", "dumpling", "dumplings", "pot stickers"},
    {"edamame", "soy beans", "soybeans"},
    {"bao", "buns", "bao buns"},
    {"poke", "poké", "poke bowl"},
    {"miso", "miso soup"},
    {"sake", "rice wine"},
    {"matcha", "green tea"},
    {"wonton", "wontons"},
    {"spring roll", "spring rolls", "egg roll", "egg rolls"},
    {"kimchi", "kim chi"},
    {"bulgogi", "korean bbq beef"},

    # Indian
    {"curry", "masala"},
    {"naan", "naan bread"},
    {"tikka", "tikka masala"},
    {"paneer", "indian cheese"},
    {"samosa", "samosas"},
    {"biryani", "biriyani"},
    {"tandoori", "tandoor"},

    # Italian
    {"pizza", "pie", "pies"},
    {"pepperoni", "pep"},
    {"calzone", "calzones"},
    {"bruschetta", "bruschettas"},
    {"gnocchi", "gnocco"},
    {"risotto", "rice dish"},
    {"prosciutto", "italian ham"},

    # Mediterranean / Middle Eastern
    {"hummus", "hummos"},
    {"falafel", "falafels"},
    {"gyro", "gyros", "shawarma"},
    {"kabob", "kebab", "kebob", "kabab"},
    {"pita", "pita bread"},
    {"tzatziki", "tzaziki"},
    {"baklava", "baklawa"},
    {"tahini", "tahina"},
    {"dolma", "dolmas", "dolmades", "stuffed grape leaves"},

    # American comfort
    {"sandwich", "sando", "sammy", "sub", "hoagie"},
    {"wrap", "wraps"},
    {"melt", "melts"},
    {"hot dog", "hotdog", "frank", "frankfurter"},
    {"fries", "french fries", "chips"},
    {"nachos", "nacho"},
    {"chili", "chile con carne"},
    {"cornbread", "corn bread"},

    # Salads
    {"salad", "ensalada"},
    {"caesar", "caeser"},

    # Soups
    {"soup", "sopa", "broth", "stew"},
    {"chowder", "clam chowder"},
    {"bisque", "bisque soup"},
    {"gazpacho", "cold soup"},

    # Eggs / breakfast
    {"egg", "eggs", "huevo", "huevos"},
    {"omelette", "omelet", "omlette"},
    {"benedict", "eggs benedict"},
    {"pancake", "pancakes", "hotcake", "hotcakes", "flapjack", "flapjacks"},
    {"waffle", "waffles"},
    {"french toast", "frenchtoast", "french-toast"},
    {"crepe", "crepes", "crêpe"},
    {"bagel", "bagels"},
    {"croissant", "croissants"},
    {"granola", "muesli"},
    {"oatmeal", "oats", "porridge"},

    # Drinks
    {"coffee", "joe", "java"},
    {"latte", "lattes", "cafe latte"},
    {"cappuccino", "cap"},
    {"espresso", "expresso"},
    {"mocha", "cafe mocha"},
    {"americano", "long black"},
    {"machiatto", "macchiato"},
    {"tea", "chai"},
    {"smoothie", "smoothies"},
    {"juice", "juices"},
    {"soda", "pop", "soft drink", "softdrink"},
    {"coke", "coca-cola", "cocacola", "coca cola"},
    {"sprite", "lemon-lime"},
    {"lemonade", "lemonades"},
    {"milkshake", "milk shake", "shake"},
    {"beer", "lager", "ale", "ipa", "pilsner", "stout"},
    {"wine", "vino"},
    {"cocktail", "cocktails", "drink", "mixed drink"},
    {"margarita", "margaritas"},
    {"mojito", "mojitos"},

    # Desserts
    {"dessert", "desserts", "postre", "sweet"},
    {"cake", "cakes", "torte"},
    {"cheesecake", "cheese cake"},
    {"brownie", "brownies"},
    {"cookie", "cookies", "biscuit", "biscuits"},
    {"ice cream", "icecream", "gelato"},
    {"sorbet", "sherbet"},
    {"pudding", "puddings"},
    {"pie", "pies", "tart", "tarts"},
    {"donut", "doughnut", "donuts", "doughnuts"},
    {"churros", "churro"},
    {"flan", "creme caramel"},
    {"tres leches", "tres leches cake"},

    # Generic
    {"spicy", "hot", "picante"},
    {"sweet", "dulce"},
    {"sour", "agrio", "tangy"},
    {"crispy", "crunchy", "crisp"},
    {"grilled", "asado", "char-grilled", "chargrilled"},
    {"fried", "frito"},
    {"baked", "horneado"},
    {"smoked", "smoke"},
    {"roasted", "rostizado"},
    {"steamed", "vapor"},
    {"raw", "crudo"},
    {"vegan", "plant-based", "plant based"},
    {"vegetarian", "veggie", "veg"},
    {"gluten free", "gluten-free", "glutenfree", "gf"},
    {"low carb", "low-carb", "lowcarb", "keto"},
]


def _build_synonym_map(groups: list[set[str]]) -> dict[str, set[str]]:
    """Build a flat lookup: word -> set of all words in its group (excluding itself)."""
    result: dict[str, set[str]] = {}
    for group in groups:
        for word in group:
            others = group - {word}
            if word in result:
                result[word] |= others
            else:
                result[word] = set(others)
    return result


SYNONYM_MAP: dict[str, set[str]] = _build_synonym_map(_SYNONYM_GROUPS)


def expand_word(word: str) -> set[str]:
    """Return the word plus all its synonyms (case-insensitive)."""
    word_lower = word.lower()
    return {word_lower} | SYNONYM_MAP.get(word_lower, set())


def expand_query_words(words: list[str]) -> dict[str, set[str]]:
    """For each query word, return the set of equivalent words to search for.

    Returns: { original_word: {original_word, syn1, syn2, ...} }
    """
    return {w: expand_word(w) for w in words}
