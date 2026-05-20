import Foundation
import MapKit
import SwiftData

@Observable
final class MapViewModel {
    var searchQuery: String = ""
    var restaurants: [Restaurant] = []
    var selectedRestaurant: Restaurant?
    var isLoading: Bool = false
    var errorMessage: String?
    var showBottomSheet: Bool = false
    var hasSearchedCurrentArea: Bool = true

    var cameraPosition: MapCameraPosition = .automatic
    var visibleRegion: MKCoordinateRegion?

    private let apiClient = APIClient.shared

    /// The center coordinate to use for searching (either visible region center or user location)
    var searchCenter: CLLocationCoordinate2D? {
        visibleRegion?.center
    }

    /// Search radius based on the visible map region (in meters)
    var searchRadius: Double {
        guard let region = visibleRegion else { return 5000 }
        let span = region.span
        let latMeters = span.latitudeDelta * 111_320
        let lngMeters = span.longitudeDelta * 111_320 * cos(region.center.latitude * .pi / 180)
        return min(max(latMeters, lngMeters) / 2, 50_000)
    }

    // MARK: - Search

    /// Perform a menu item search at the current map location
    func search(at coordinate: CLLocationCoordinate2D? = nil) async {
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }

        let center = coordinate ?? searchCenter
        guard let center else { return }

        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiClient.searchMenuItems(
                query: query,
                lat: center.latitude,
                lng: center.longitude,
                radius: searchRadius
            )

            restaurants = response.restaurants
            hasSearchedCurrentArea = true
            showBottomSheet = !restaurants.isEmpty

            // Fit the map to show all results
            if !restaurants.isEmpty {
                updateCameraToFitResults()
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    /// Called when the user pans or zooms the map
    func onRegionChanged(_ region: MKCoordinateRegion) {
        let oldCenter = visibleRegion?.center
        visibleRegion = region

        // Mark as needing re-search if moved significantly
        if let old = oldCenter {
            let distance = CLLocation(latitude: old.latitude, longitude: old.longitude)
                .distance(from: CLLocation(latitude: region.center.latitude, longitude: region.center.longitude))
            if distance > 500 && !searchQuery.isEmpty {
                hasSearchedCurrentArea = false
            }
        }
    }

    /// Search the currently visible area
    func searchThisArea() async {
        await search()
    }

    /// Select a restaurant and center the map on it
    func selectRestaurant(_ restaurant: Restaurant) {
        selectedRestaurant = restaurant
        cameraPosition = .region(MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: restaurant.lat, longitude: restaurant.lng),
            span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
        ))
    }

    /// Clear the current search
    func clearSearch() {
        searchQuery = ""
        restaurants = []
        showBottomSheet = false
        selectedRestaurant = nil
        hasSearchedCurrentArea = true
    }

    // MARK: - Private

    private func updateCameraToFitResults() {
        guard !restaurants.isEmpty else { return }

        var minLat = restaurants[0].lat
        var maxLat = restaurants[0].lat
        var minLng = restaurants[0].lng
        var maxLng = restaurants[0].lng

        for r in restaurants {
            minLat = min(minLat, r.lat)
            maxLat = max(maxLat, r.lat)
            minLng = min(minLng, r.lng)
            maxLng = max(maxLng, r.lng)
        }

        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLng + maxLng) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: max((maxLat - minLat) * 1.4, 0.01),
            longitudeDelta: max((maxLng - minLng) * 1.4, 0.01)
        )

        cameraPosition = .region(MKCoordinateRegion(center: center, span: span))
    }
}
