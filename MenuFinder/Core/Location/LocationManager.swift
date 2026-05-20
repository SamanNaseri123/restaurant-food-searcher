import Foundation
import CoreLocation

@Observable
final class LocationManager: NSObject, CLLocationManagerDelegate {
    var currentLocation: CLLocationCoordinate2D?
    var authorizationStatus: CLAuthorizationStatus = .notDetermined
    var locationError: Error?

    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        authorizationStatus = manager.authorizationStatus
    }

    // MARK: - Public

    /// Request location permission from the user
    func requestPermission() {
        manager.requestWhenInUseAuthorization()
    }

    /// Request a single location update
    func requestLocation() {
        guard authorizationStatus == .authorizedWhenInUse ||
              authorizationStatus == .authorizedAlways else {
            requestPermission()
            return
        }
        manager.requestLocation()
    }

    /// Start continuous location updates
    func startUpdating() {
        manager.startUpdatingLocation()
    }

    /// Stop continuous location updates
    func stopUpdating() {
        manager.stopUpdatingLocation()
    }

    /// Whether location services are available
    var isAuthorized: Bool {
        authorizationStatus == .authorizedWhenInUse ||
        authorizationStatus == .authorizedAlways
    }

    // MARK: - CLLocationManagerDelegate

    func locationManager(
        _ manager: CLLocationManager,
        didUpdateLocations locations: [CLLocation]
    ) {
        guard let location = locations.last else { return }
        currentLocation = location.coordinate
        locationError = nil
    }

    func locationManager(
        _ manager: CLLocationManager,
        didFailWithError error: Error
    ) {
        locationError = error
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus

        if isAuthorized {
            manager.requestLocation()
        }
    }
}
