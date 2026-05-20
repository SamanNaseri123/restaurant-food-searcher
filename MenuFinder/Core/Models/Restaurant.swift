import Foundation

// MARK: - Restaurant

struct Restaurant: Identifiable, Codable, Hashable {
    let id: UUID
    let name: String
    let address: String
    let lat: Double
    let lng: Double
    let websiteUrl: String?
    let phone: String?
    let rating: Double?
    let priceLevel: Int?
    let photos: [String]
    let distanceMeters: Double?
    let matchedItems: [MenuItem]

    enum CodingKeys: String, CodingKey {
        case id, name, address, lat, lng
        case websiteUrl = "website_url"
        case phone, rating
        case priceLevel = "price_level"
        case photos
        case distanceMeters = "distance_meters"
        case matchedItems = "matched_items"
    }

    /// Returns a price level string like "$", "$$", "$$$"
    var priceLevelString: String? {
        guard let level = priceLevel, level > 0 else { return nil }
        return String(repeating: "$", count: min(level, 4))
    }

    /// Color tier based on number of matched items
    var matchTier: MatchTier {
        let count = matchedItems.count
        if count >= 3 { return .best }
        if count >= 1 { return .good }
        return .hasItem
    }
}

enum MatchTier {
    case best, good, hasItem

    var color: String {
        switch self {
        case .best: return "green"
        case .good: return "orange"
        case .hasItem: return "red"
        }
    }
}

// MARK: - MenuItem

struct MenuItem: Identifiable, Codable, Hashable {
    let id: UUID
    let name: String
    let description: String?
    let price: Double?
    let category: String?

    /// Formatted price string
    var formattedPrice: String? {
        guard let price else { return nil }
        return String(format: "$%.2f", price)
    }
}

// MARK: - API Responses

struct SearchResponse: Codable {
    let query: String
    let lat: Double
    let lng: Double
    let radiusMeters: Double
    let totalResults: Int
    let restaurants: [Restaurant]

    enum CodingKeys: String, CodingKey {
        case query, lat, lng
        case radiusMeters = "radius_meters"
        case totalResults = "total_results"
        case restaurants
    }
}

struct AutocompleteResponse: Codable {
    let suggestions: [String]
}
