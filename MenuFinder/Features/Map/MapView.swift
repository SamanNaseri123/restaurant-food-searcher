import SwiftUI
import MapKit

struct MapView: View {
    @Environment(LocationManager.self) private var locationManager
    @State private var viewModel = MapViewModel()
    @State private var searchViewModel = SearchViewModel()
    @State private var selectedDetent: PresentationDetent = .medium
    @State private var navigateToDetail: Restaurant?

    var body: some View {
        NavigationStack {
            ZStack {
                // MARK: - Map
                mapContent

                // MARK: - Overlays
                VStack(spacing: 0) {
                    // Search bar at top
                    SearchBar(
                        text: $viewModel.searchQuery,
                        searchViewModel: searchViewModel,
                        onSubmit: {
                            Task { await viewModel.search(at: locationManager.currentLocation) }
                        },
                        onSuggestionSelected: { suggestion in
                            viewModel.searchQuery = suggestion
                            Task { await viewModel.search(at: locationManager.currentLocation) }
                        }
                    )
                    .padding(.horizontal)
                    .padding(.top, 8)

                    Spacer()

                    // "Search this area" button
                    if !viewModel.hasSearchedCurrentArea {
                        Button {
                            Task { await viewModel.searchThisArea() }
                        } label: {
                            Label("Search this area", systemImage: "arrow.clockwise")
                                .font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(.ultraThinMaterial)
                                .clipShape(Capsule())
                                .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
                        }
                        .padding(.bottom, 16)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                        .animation(.spring(duration: 0.3), value: viewModel.hasSearchedCurrentArea)
                    }

                    // Loading indicator
                    if viewModel.isLoading {
                        ProgressView()
                            .controlSize(.large)
                            .padding()
                            .background(.ultraThinMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .shadow(radius: 8)
                            .padding(.bottom, 20)
                    }
                }

                // Error banner
                if let error = viewModel.errorMessage {
                    VStack {
                        Spacer()
                        errorBanner(error)
                            .padding()
                            .padding(.bottom, 60)
                    }
                }
            }
            .sheet(isPresented: $viewModel.showBottomSheet) {
                bottomSheetContent
                    .presentationDetents([.medium, .large], selection: $selectedDetent)
                    .presentationDragIndicator(.visible)
                    .presentationBackgroundInteraction(.enabled(upThrough: .medium))
                    .presentationCornerRadius(20)
            }
            .navigationDestination(item: $navigateToDetail) { restaurant in
                RestaurantDetailView(
                    restaurant: restaurant,
                    searchQuery: viewModel.searchQuery
                )
            }
            .onAppear {
                locationManager.requestPermission()
                if let location = locationManager.currentLocation {
                    viewModel.cameraPosition = .region(MKCoordinateRegion(
                        center: location,
                        span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                    ))
                }
            }
            .onChange(of: locationManager.currentLocation) { _, newLocation in
                if let location = newLocation, viewModel.visibleRegion == nil {
                    viewModel.cameraPosition = .region(MKCoordinateRegion(
                        center: location,
                        span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                    ))
                }
            }
        }
    }

    // MARK: - Map Content

    private var mapContent: some View {
        Map(position: $viewModel.cameraPosition, selection: $viewModel.selectedRestaurant) {
            // User location
            UserAnnotation()

            // Restaurant markers
            ForEach(viewModel.restaurants) { restaurant in
                Annotation(
                    restaurant.name,
                    coordinate: CLLocationCoordinate2D(
                        latitude: restaurant.lat,
                        longitude: restaurant.lng
                    ),
                    anchor: .bottom
                ) {
                    restaurantMarker(for: restaurant)
                        .onTapGesture {
                            viewModel.selectRestaurant(restaurant)
                        }
                }
                .tag(restaurant)
            }
        }
        .mapStyle(.standard(pointsOfInterest: .including([.restaurant, .foodMarket])))
        .mapControls {
            MapUserLocationButton()
            MapCompass()
            MapScaleView()
        }
        .onMapCameraChange(frequency: .onEnd) { context in
            viewModel.onRegionChanged(context.region)
        }
        .ignoresSafeArea(edges: .top)
    }

    // MARK: - Restaurant Marker

    private func restaurantMarker(for restaurant: Restaurant) -> some View {
        VStack(spacing: 2) {
            Image(systemName: "fork.knife.circle.fill")
                .font(.title)
                .foregroundStyle(.white, markerColor(for: restaurant))
                .shadow(color: markerColor(for: restaurant).opacity(0.4), radius: 4, y: 2)

            if restaurant == viewModel.selectedRestaurant {
                Text(restaurant.name)
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.ultraThinMaterial)
                    .clipShape(Capsule())
            }
        }
    }

    private func markerColor(for restaurant: Restaurant) -> Color {
        switch restaurant.matchTier {
        case .best: return .green
        case .good: return .orange
        case .hasItem: return .red
        }
    }

    // MARK: - Bottom Sheet

    private var bottomSheetContent: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(viewModel.restaurants) { restaurant in
                        RestaurantCardView(
                            restaurant: restaurant,
                            searchQuery: viewModel.searchQuery
                        )
                        .onTapGesture {
                            navigateToDetail = restaurant
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("\(viewModel.restaurants.count) Results")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        viewModel.showBottomSheet = false
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }

    // MARK: - Error Banner

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)

            Text(message)
                .font(.subheadline)
                .foregroundStyle(.white)
                .lineLimit(2)

            Spacer()

            Button {
                viewModel.errorMessage = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        .padding()
        .background(.red.gradient, in: RoundedRectangle(cornerRadius: 12))
        .shadow(color: .red.opacity(0.3), radius: 8, y: 4)
    }
}

#Preview {
    MapView()
        .environment(LocationManager())
}
