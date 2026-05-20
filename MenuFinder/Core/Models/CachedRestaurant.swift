import Foundation
import SwiftData

// MARK: - CachedRestaurant

@Model
final class CachedRestaurant {
    @Attribute(.unique) var restaurantId: UUID
    var name: String
    var address: String
    var lat: Double
    var lng: Double
    var websiteUrl: String?
    var phone: String?
    var rating: Double?
    var priceLevel: Int?
    var photos: [String]
    var matchedItemsData: Data?
    var cachedAt: Date

    init(from restaurant: Restaurant) {
        self.restaurantId = restaurant.id
        self.name = restaurant.name
        self.address = restaurant.address
        self.lat = restaurant.lat
        self.lng = restaurant.lng
        self.websiteUrl = restaurant.websiteUrl
        self.phone = restaurant.phone
        self.rating = restaurant.rating
        self.priceLevel = restaurant.priceLevel
        self.photos = restaurant.photos
        self.matchedItemsData = try? JSONEncoder().encode(restaurant.matchedItems)
        self.cachedAt = Date()
    }

    /// Convert back to a Restaurant model
    func toRestaurant(distanceMeters: Double? = nil) -> Restaurant {
        let items: [MenuItem] = {
            guard let data = matchedItemsData else { return [] }
            return (try? JSONDecoder().decode([MenuItem].self, from: data)) ?? []
        }()

        return Restaurant(
            id: restaurantId,
            name: name,
            address: address,
            lat: lat,
            lng: lng,
            websiteUrl: websiteUrl,
            phone: phone,
            rating: rating,
            priceLevel: priceLevel,
            photos: photos,
            distanceMeters: distanceMeters,
            matchedItems: items
        )
    }

    /// Whether the cache entry is still fresh (within 1 hour)
    var isFresh: Bool {
        Date().timeIntervalSince(cachedAt) < 3600
    }
}

// MARK: - CachedSearchResult

@Model
final class CachedSearchResult {
    @Attribute(.unique) var cacheKey: String
    var query: String
    var resultsData: Data
    var cachedAt: Date

    init(query: String, lat: Double, lng: Double, radius: Double, response: SearchResponse) {
        self.cacheKey = "\(query)_\(lat)_\(lng)_\(radius)"
        self.query = query
        self.resultsData = (try? JSONEncoder().encode(response)) ?? Data()
        self.cachedAt = Date()
    }

    /// Decode the cached search response
    func toSearchResponse() -> SearchResponse? {
        try? JSONDecoder().decode(SearchResponse.self, from: resultsData)
    }

    /// Whether the cache entry is still fresh (within 30 minutes)
    var isFresh: Bool {
        Date().timeIntervalSince(cachedAt) < 1800
    }

    /// Generate a cache key for lookups
    static func key(query: String, lat: Double, lng: Double, radius: Double) -> String {
        "\(query)_\(lat)_\(lng)_\(radius)"
    }
}
