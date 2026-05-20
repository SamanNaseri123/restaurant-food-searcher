import Foundation

// MARK: - APIClient

actor APIClient {
    static let shared = APIClient()

    private let baseURL: String
    private let session: URLSession

    init(baseURL: String = "http://localhost:8000") {
        self.baseURL = baseURL

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)
    }

    // MARK: - Search

    /// Search for menu items near a location
    func searchMenuItems(
        query: String,
        lat: Double,
        lng: Double,
        radius: Double = 5000
    ) async throws -> SearchResponse {
        var components = URLComponents(string: "\(baseURL)/api/search")!
        components.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "lat", value: String(lat)),
            URLQueryItem(name: "lng", value: String(lng)),
            URLQueryItem(name: "radius", value: String(Int(radius)))
        ]

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        return try await fetch(url: url)
    }

    // MARK: - Restaurant Detail

    /// Get full details for a single restaurant
    func getRestaurant(id: UUID) async throws -> Restaurant {
        guard let url = URL(string: "\(baseURL)/api/restaurants/\(id.uuidString)") else {
            throw APIError.invalidURL
        }

        return try await fetch(url: url)
    }

    // MARK: - Autocomplete

    /// Get autocomplete suggestions for a partial query
    func autocomplete(query: String) async throws -> [String] {
        var components = URLComponents(string: "\(baseURL)/api/autocomplete")!
        components.queryItems = [
            URLQueryItem(name: "q", value: query)
        ]

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        let response: AutocompleteResponse = try await fetch(url: url)
        return response.suggestions
    }

    // MARK: - Private

    private func fetch<T: Decodable>(url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError(statusCode: httpResponse.statusCode)
        }

        let decoder = JSONDecoder()
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }
}

// MARK: - APIError

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .httpError(let code):
            return "Server error (HTTP \(code))"
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        }
    }
}
