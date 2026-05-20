import hashlib
import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import Boolean, Float, case, cast, func, literal, or_, select, text
from geoalchemy2 import Geography
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import re as _re

# Common short stopwords filtered from query word lists
_STOPWORDS = {
    "and", "the", "with", "for", "are", "was", "this", "that", "from", "but",
    "not", "you", "all", "any", "our", "your", "out", "off", "have", "has",
}


def _word_in_text(word: str, text: str) -> bool:
    """Check if `word` appears as a whole word in `text` (case-insensitive)."""
    return bool(_re.search(rf"\b{_re.escape(word)}\b", text, _re.IGNORECASE))


def _any_synonym_in_text(synonyms: set[str], text: str) -> bool:
    """Check if any of the given synonyms appears as a whole word in text."""
    for word in synonyms:
        if _word_in_text(word, text):
            return True
    return False

# Radius (meters) used for IDF frequency calculations.
# Fixed at ~10 miles to give locally-relevant stats regardless of search radius.
_IDF_RADIUS_METERS = 16093

from app.api.schemas import (
    AutocompleteResponse,
    MenuItemResult,
    RestaurantDetailResponse,
    RestaurantResult,
    SearchResponse,
)
from app.models.restaurant import MenuItem, Restaurant, SearchCache
from app.services.food_synonyms import expand_query_words


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int,
        sort_by: str = "relevance",
        limit: int = 20,
    ) -> SearchResponse:
        # Check cache first
        cache_key = self._cache_key(query, lat, lng, radius_meters)
        cached = await self._get_cached(cache_key)
        if cached:
            return SearchResponse(**cached)

        # Build the search point
        point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)

        # Multi-tier search strategy (like Google/Bing):
        # 1. Full-text search (exact word matches, stemmed) — "mac and cheese" matches "macaroni cheese"
        # 2. Phrase prefix matching — "mac and cheese" as substring
        # 3. Individual word matching — "mac" OR "cheese" in name (catches "Lobster Mac", "Grilled Cheese")
        # 4. Trigram similarity (typos: "buger" -> "burger")
        ts_query = func.plainto_tsquery("english", query)
        prefix_pattern = f"%{query}%"

        # Split query into meaningful words (drop short tokens and stopwords)
        query_words = [
            w for w in query.lower().split()
            if len(w) >= 3 and w not in _STOPWORDS
        ]
        # Expand each query word with its synonyms (mac -> {mac, macaroni}).
        # SQL match condition: for each query word, OR its synonyms together.
        # Use word boundaries (\y) to avoid false positives like "Macchiato".
        synonym_expansion = expand_query_words(query_words)
        word_conditions = []
        for w, synonyms in synonym_expansion.items():
            # Match if ANY synonym appears at word boundaries
            syn_conditions = [
                MenuItem.name.op("~*")(rf"\y{_re.escape(s)}\y") for s in synonyms
            ]
            if len(syn_conditions) == 1:
                word_conditions.append(syn_conditions[0])
            else:
                word_conditions.append(or_(*syn_conditions))

        # Trigram similarity on name and description
        name_similarity = func.similarity(MenuItem.name, query)
        desc_similarity = func.coalesce(
            func.similarity(MenuItem.description, query), literal(0.0)
        )
        trgm_score = name_similarity + desc_similarity

        # Rank: full-text > phrase prefix > word match > trigram
        rank_score = case(
            (MenuItem.search_vector.op("@@")(ts_query), literal(10.0) + func.ts_rank(MenuItem.search_vector, ts_query)),
            (MenuItem.name.ilike(prefix_pattern), literal(5.0)),
            else_=trgm_score,
        )

        # Build match conditions
        match_conditions = [
            MenuItem.search_vector.op("@@")(ts_query),
            MenuItem.name.ilike(prefix_pattern),
            name_similarity > 0.15,
            desc_similarity > 0.15,
        ]
        # Add individual word matches (any word in name)
        match_conditions.extend(word_conditions)

        stmt = (
            select(
                Restaurant,
                MenuItem,
                ST_Distance(
                    cast(Restaurant.location, Geography),
                    cast(point, Geography),
                    type_=Float,
                ).label("distance"),
                rank_score.label("rank"),
            )
            .join(MenuItem, MenuItem.restaurant_id == Restaurant.id)
            .where(
                ST_DWithin(
                    cast(Restaurant.location, Geography),
                    cast(point, Geography),
                    radius_meters,
                    type_=Boolean,
                ),
                or_(*match_conditions),
            )
            .order_by(text("rank DESC"), text("distance ASC"))
            .limit(5000)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # Group by restaurant
        # Extract coordinates for all restaurants in one query
        restaurant_ids = list({row[0].id for row in rows})
        coord_map: dict[UUID, tuple[float, float]] = {}
        if restaurant_ids:
            coord_stmt = select(
                Restaurant.id,
                func.ST_Y(Restaurant.location).label("lat"),
                func.ST_X(Restaurant.location).label("lng"),
            ).where(Restaurant.id.in_(restaurant_ids))
            coord_result = await self.db.execute(coord_stmt)
            for r_id, r_lat, r_lng in coord_result.all():
                coord_map[r_id] = (r_lat, r_lng)

        restaurants_map: dict[UUID, RestaurantResult] = {}
        for restaurant, menu_item, distance, rank in rows:
            r_id = restaurant.id
            if r_id not in restaurants_map:
                r_lat, r_lng = coord_map.get(r_id, (lat, lng))
                restaurants_map[r_id] = RestaurantResult(
                    id=r_id,
                    name=restaurant.name,
                    address=restaurant.address,
                    lat=r_lat,
                    lng=r_lng,
                    website_url=restaurant.website_url,
                    phone=restaurant.phone,
                    rating=restaurant.rating,
                    price_level=restaurant.price_level,
                    photos=restaurant.photos or [],
                    distance_miles=round(distance / 1609.34, 1) if distance else None,
                    matched_items=[],
                )

            restaurants_map[r_id].matched_items.append(
                MenuItemResult(
                    id=menu_item.id,
                    name=menu_item.name,
                    description=menu_item.description,
                    price=menu_item.price,
                    category=menu_item.category,
                )
            )

        # For relevance sort: compute IDF + co-occurrence for TF-IDF-style ranking
        word_idf: dict[str, float] = {}
        cooccurrence: dict[str, dict[str, float]] = {}
        if sort_by == "relevance" and query_words:
            try:
                word_idf = await self._compute_word_idf(query_words, point)
                cooccurrence = await self._compute_cooccurrence(query_words, point)
            except Exception:
                word_idf = {}
                cooccurrence = {}

        all_sorted = self._sort_results(
            list(restaurants_map.values()),
            sort_by,
            query_words=query_words,
            word_idf=word_idf,
            cooccurrence=cooccurrence,
            synonyms=synonym_expansion,
        )
        total = len(all_sorted)
        restaurants_list = all_sorted[:limit]

        response = SearchResponse(
            query=query,
            lat=lat,
            lng=lng,
            radius_miles=round(radius_meters / 1609.34, 1),
            total_results=total,
            restaurants=restaurants_list,
        )

        return response

    async def get_restaurant_detail(self, restaurant_id: UUID) -> RestaurantDetailResponse:
        stmt = (
            select(Restaurant)
            .options(selectinload(Restaurant.menu_items))
            .where(Restaurant.id == restaurant_id)
        )
        result = await self.db.execute(stmt)
        restaurant = result.scalar_one_or_none()

        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        # Extract lat/lng from PostGIS point
        coord_stmt = select(
            func.ST_Y(restaurant.location).label("lat"),
            func.ST_X(restaurant.location).label("lng"),
        )
        coord_result = await self.db.execute(coord_stmt)
        coords = coord_result.one()

        return RestaurantDetailResponse(
            id=restaurant.id,
            name=restaurant.name,
            address=restaurant.address,
            lat=coords.lat,
            lng=coords.lng,
            website_url=restaurant.website_url,
            phone=restaurant.phone,
            rating=restaurant.rating,
            price_level=restaurant.price_level,
            photos=restaurant.photos or [],
            menu_items=[
                MenuItemResult(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    price=item.price,
                    category=item.category,
                )
                for item in restaurant.menu_items
            ],
            menu_last_scraped_at=restaurant.menu_last_scraped_at,
        )

    async def autocomplete(self, query: str) -> AutocompleteResponse:
        # Combine prefix matching + trigram similarity for autocomplete
        prefix_pattern = f"%{query}%"
        name_similarity = func.similarity(MenuItem.name, query)

        stmt = (
            select(MenuItem.name, name_similarity.label("sim"))
            .where(
                or_(
                    MenuItem.name.ilike(prefix_pattern),
                    name_similarity > 0.15,
                    MenuItem.search_vector.op("@@")(
                        func.plainto_tsquery("english", query)
                    ),
                )
            )
            .distinct()
            .order_by(text("sim DESC"))
            .limit(10)
        )
        result = await self.db.execute(stmt)
        suggestions = [row[0] for row in result.all()]
        return AutocompleteResponse(suggestions=suggestions)

    async def _compute_cooccurrence(
        self, query_words: list[str], point
    ) -> dict[str, dict[str, float]]:
        """For each query word, compute the fraction of items containing it that
        also contain each other query word.

        E.g. if 95% of items with "mac" in the name also contain "cheese",
        then cooccurrence["mac"]["cheese"] = 0.95.

        This captures the intuition that "mac" alone usually means "mac and cheese"
        in restaurant menus.
        """
        if len(query_words) < 2:
            return {}

        result: dict[str, dict[str, float]] = {}
        for word in query_words:
            other_words = [w for w in query_words if w != word]
            if not other_words:
                continue

            # Count items with `word` in name, and how many of those also have each other word
            count_word = func.sum(
                case((MenuItem.name.op("~*")(rf"\y{word}\y"), 1), else_=0)
            ).label("base")
            cooccur_exprs = [
                func.sum(
                    case(
                        (
                            MenuItem.name.op("~*")(rf"\y{word}\y")
                            & MenuItem.name.op("~*")(rf"\y{other}\y"),
                            1,
                        ),
                        else_=0,
                    )
                ).label(f"co_{i}")
                for i, other in enumerate(other_words)
            ]

            stmt = (
                select(count_word, *cooccur_exprs)
                .select_from(MenuItem)
                .join(Restaurant, MenuItem.restaurant_id == Restaurant.id)
                .where(
                    ST_DWithin(
                        cast(Restaurant.location, Geography),
                        cast(point, Geography),
                        _IDF_RADIUS_METERS,
                        type_=Boolean,
                    )
                )
            )
            row = (await self.db.execute(stmt)).one()
            base = int(row.base or 0)
            if base == 0:
                continue

            result[word] = {}
            for i, other in enumerate(other_words):
                co_count = int(getattr(row, f"co_{i}") or 0)
                result[word][other] = co_count / base

        return result

    async def _compute_word_idf(
        self, query_words: list[str], point
    ) -> dict[str, float]:
        """Compute IDF for each query word using items in a fixed local radius.

        IDF (Inverse Document Frequency) measures word rarity — rare words get
        higher scores. This is the core component of TF-IDF / BM25, used by
        Elasticsearch, Lucene, and Solr for relevance ranking.

        For "mac and cheese", "mac" is rarer than "cheese" in restaurant menus,
        so items containing "mac" get scored higher.

        Uses a single SQL query with CASE expressions to count all words at once.
        """
        if not query_words:
            return {}

        count_exprs = [
            func.sum(
                case((MenuItem.name.op("~*")(rf"\y{word}\y"), 1), else_=0)
            ).label(f"w_{i}")
            for i, word in enumerate(query_words)
        ]

        stmt = (
            select(func.count(MenuItem.id).label("total"), *count_exprs)
            .select_from(MenuItem)
            .join(Restaurant, MenuItem.restaurant_id == Restaurant.id)
            .where(
                ST_DWithin(
                    cast(Restaurant.location, Geography),
                    cast(point, Geography),
                    _IDF_RADIUS_METERS,
                    type_=Boolean,
                )
            )
        )

        result = await self.db.execute(stmt)
        row = result.one()

        total = int(row.total or 0)
        if total == 0:
            return {w: 0.0 for w in query_words}

        word_idf: dict[str, float] = {}
        for i, word in enumerate(query_words):
            count = int(getattr(row, f"w_{i}") or 0)
            # BM25-style IDF: log((N - n + 0.5) / (n + 0.5) + 1)
            # +1 inside log keeps it positive even when n is large
            word_idf[word] = max(
                0.0, math.log((total - count + 0.5) / (count + 0.5) + 1)
            )
        return word_idf

    @staticmethod
    def _sort_results(
        restaurants: list[RestaurantResult],
        sort_by: str,
        query_words: list[str] | None = None,
        word_idf: dict[str, float] | None = None,
        cooccurrence: dict[str, dict[str, float]] | None = None,
        synonyms: dict[str, set[str]] | None = None,
    ) -> list[RestaurantResult]:
        if sort_by == "distance":
            return sorted(restaurants, key=lambda r: r.distance_miles or float("inf"))
        elif sort_by == "rating":
            return sorted(restaurants, key=lambda r: -(r.rating or 0))
        elif sort_by == "price_low":
            def avg_price(r):
                prices = [i.price for i in r.matched_items if i.price]
                return sum(prices) / len(prices) if prices else float("inf")
            return sorted(restaurants, key=avg_price)
        elif sort_by == "price_high":
            def avg_price_desc(r):
                prices = [i.price for i in r.matched_items if i.price]
                return -(sum(prices) / len(prices)) if prices else 0
            return sorted(restaurants, key=avg_price_desc)
        else:  # relevance (default)
            return SearchService._sort_by_relevance_tiered(
                restaurants,
                query_words or [],
                word_idf or {},
                cooccurrence=cooccurrence or {},
                synonyms=synonyms,
            )

    @staticmethod
    def _rank_matched_items(
        items: list[MenuItemResult],
        query_words: list[str],
        word_idf: dict[str, float],
        max_items: int | None = None,
        cooccurrence: dict[str, dict[str, float]] | None = None,
        cooccurrence_threshold: float = 0.8,
        synonyms: dict[str, set[str]] | None = None,
    ) -> list[MenuItemResult]:
        """Rank items within a restaurant by relevance to the query.

        Items get credit for "effective" word matches: a word literally in the name,
        OR strongly co-occurring (>= threshold) with another query word in the name.

        E.g. "Lobster Mac" effectively contains "cheese" because "mac" co-occurs
        with "cheese" in 95% of the menu corpus.
        """
        if not query_words:
            return items[:max_items] if max_items else items

        cooccurrence = cooccurrence or {}
        synonyms = synonyms or {w: {w} for w in query_words}

        def word_or_synonym_in(word: str, text: str) -> bool:
            return _any_synonym_in_text(synonyms.get(word, {word}), text)

        def effective_words(name: str) -> set[str]:
            literal = {w for w in query_words if word_or_synonym_in(w, name)}
            effective = set(literal)
            for missing in (set(query_words) - literal):
                for present in literal:
                    if cooccurrence.get(present, {}).get(missing, 0.0) >= cooccurrence_threshold:
                        effective.add(missing)
                        break
            return effective

        def item_score(item: MenuItemResult) -> tuple[int, int, float]:
            name = item.name
            desc = item.description or ""
            full = name + " " + desc

            literal_in_name = sum(1 for w in query_words if word_or_synonym_in(w, name))
            eff_in_name = len(effective_words(name))

            relevance = sum(word_idf.get(w, 0.0) for w in query_words if word_or_synonym_in(w, full))
            relevance += sum(
                word_idf.get(w, 0.0) * 0.5 for w in query_words if word_or_synonym_in(w, name)
            )
            return eff_in_name, literal_in_name, relevance

        ranked = sorted(items, key=lambda i: item_score(i), reverse=True)
        return ranked[:max_items] if max_items else ranked

    @staticmethod
    def _sort_by_relevance_tiered(
        restaurants: list[RestaurantResult],
        query_words: list[str],
        word_idf: dict[str, float],
        distance_threshold_miles: float = 3.0,
        distance_weight: float = 0.2,
        cooccurrence: dict[str, dict[str, float]] | None = None,
        cooccurrence_threshold: float = 0.7,
        max_items_per_restaurant: int = 5,
        synonyms: dict[str, set[str]] | None = None,
    ) -> list[RestaurantResult]:
        """Two-tier relevance ranking inspired by TF-IDF / BM25 + co-occurrence.

        - Tier 1: Restaurants with a matched item that "effectively" contains ALL
          query words in its name (within `distance_threshold_miles`).
          A word is "effectively present" if either:
            (a) it literally appears in the name, OR
            (b) it strongly co-occurs (>= 80%) with another query word that's in the name.
          E.g. "Lobster Mac" effectively contains "cheese" because in our menu corpus,
          "mac" appears with "cheese" in 95% of cases.
          Sorted by distance ascending (closest first).

        - Tier 2: Everything else. Sorted by combined score:
              relevance + name_bonus - distance_penalty
          where:
            - relevance = sum of IDF for query words found in name/description
            - name_bonus = 0.3 * (number of query words in name)
            - distance_penalty = distance_weight * distance_miles
        """
        if not query_words:
            return sorted(
                restaurants,
                key=lambda r: (-len(r.matched_items), r.distance_miles or float("inf")),
            )

        cooccurrence = cooccurrence or {}
        synonyms = synonyms or {w: {w} for w in query_words}

        def word_or_synonym_in(word: str, text: str) -> bool:
            return _any_synonym_in_text(synonyms.get(word, {word}), text)

        def effective_name_words(name: str) -> int:
            """Count query words 'effectively' present (literal + synonyms + co-occurrence).
            Uses word boundaries — "mac" matches "Lobster Mac" or "Lobster Macaroni"
            but NOT "Macchiato"."""
            literal_words = {w for w in query_words if word_or_synonym_in(w, name)}
            effective = set(literal_words)
            for missing in (set(query_words) - literal_words):
                for present in literal_words:
                    co = cooccurrence.get(present, {}).get(missing, 0.0)
                    if co >= cooccurrence_threshold:
                        effective.add(missing)
                        break
            return len(effective)

        def score_restaurant(r: RestaurantResult) -> tuple[int, int, float]:
            """Returns (effective_name_words, literal_name_words, relevance)."""
            best_eff = 0
            best_literal = 0
            best_relevance = 0.0

            for item in r.matched_items:
                name = item.name
                desc = item.description or ""
                full = name + " " + desc

                literal_words = sum(1 for w in query_words if word_or_synonym_in(w, name))
                eff_words = effective_name_words(name)

                relevance = sum(word_idf.get(w, 0.0) for w in query_words if word_or_synonym_in(w, full))
                relevance += sum(
                    word_idf.get(w, 0.0) * 0.5 for w in query_words if word_or_synonym_in(w, name)
                )

                key = (eff_words, literal_words, relevance)
                best_key = (best_eff, best_literal, best_relevance)
                if key > best_key:
                    best_eff, best_literal, best_relevance = eff_words, literal_words, relevance

            return best_eff, best_literal, best_relevance

        scored = [(r, *score_restaurant(r)) for r in restaurants]

        tier1: list[tuple] = []
        tier2: list[tuple] = []
        all_words = len(query_words)

        for r, eff_words, literal_words, relevance in scored:
            is_perfect = eff_words == all_words
            is_close = (r.distance_miles or float("inf")) <= distance_threshold_miles

            if is_perfect and is_close:
                tier1.append((r, eff_words, literal_words, relevance))
            else:
                tier2.append((r, eff_words, literal_words, relevance))

        # Tier 1: closest first, ties broken by literal match strength then relevance
        tier1.sort(key=lambda x: (
            x[0].distance_miles or float("inf"),
            -x[2],  # more literal matches first
            -x[3],  # higher relevance first
        ))

        # Tier 2: combined relevance + distance score
        def tier2_key(item):
            r, eff_words, literal_words, relevance = item
            dist = r.distance_miles if r.distance_miles is not None else 100.0
            name_bonus = literal_words * 0.3
            score = relevance + name_bonus - dist * distance_weight
            return -score

        tier2.sort(key=tier2_key)

        ordered = [r for r, *_ in tier1] + [r for r, *_ in tier2]

        # Rank and trim matched items within each restaurant.
        # Filter out items that share NO query words with the best item — keeps
        # the result focused. E.g. if best is "Mac & Cheese", don't show "Cheese Pizza".
        for r in ordered:
            r.total_matched_items = len(r.matched_items)
            ranked = SearchService._rank_matched_items(
                r.matched_items,
                query_words,
                word_idf,
                max_items=None,
                cooccurrence=cooccurrence,
                cooccurrence_threshold=cooccurrence_threshold,
                synonyms=synonyms,
            )

            def item_eff_words(item):
                name = item.name
                literal = {w for w in query_words if word_or_synonym_in(w, name)}
                effective = set(literal)
                for missing in (set(query_words) - literal):
                    for present in literal:
                        if cooccurrence.get(present, {}).get(missing, 0.0) >= cooccurrence_threshold:
                            effective.add(missing)
                            break
                return len(effective)

            if ranked:
                best_eff = item_eff_words(ranked[0])
                # If best is full coverage, drop items with zero effective coverage
                # (prevents "Cheese Pizza" from showing alongside "Mac & Cheese").
                # If best is partial, keep all items at that level or higher.
                min_eff = best_eff if best_eff >= len(query_words) else max(1, best_eff)
                filtered = [i for i in ranked if item_eff_words(i) >= min_eff]
                r.matched_items = filtered[:max_items_per_restaurant]
                r.total_matched_items = len(filtered)
            else:
                r.matched_items = []
                r.total_matched_items = 0

        ordered = [r for r in ordered if r.matched_items]
        return ordered

    def _cache_key(self, query: str, lat: float, lng: float, radius: int) -> str:
        # Round coordinates to ~100m precision for cache hits
        raw = f"{query.lower().strip()}:{round(lat, 3)}:{round(lng, 3)}:{radius}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cached(self, cache_key: str) -> dict | None:
        stmt = select(SearchCache).where(
            SearchCache.query_hash == cache_key,
            SearchCache.expires_at > datetime.now(timezone.utc),
        )
        result = await self.db.execute(stmt)
        cached = result.scalar_one_or_none()
        if cached:
            return cached.results
        return None
