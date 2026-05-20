import SwiftUI
import MapKit

struct RestaurantDetailView: View {
    let restaurant: Restaurant
    let searchQuery: String

    @State private var fullMenu: [MenuItem] = []
    @State private var isLoadingMenu: Bool = false
    @Environment(\.dismiss) private var dismiss

    /// All matched item IDs for quick lookup
    private var matchedItemIds: Set<UUID> {
        Set(restaurant.matchedItems.map(\.id))
    }

    /// Menu items grouped by category
    private var menuByCategory: [(String, [MenuItem])] {
        let grouped = Dictionary(grouping: fullMenu) { $0.category ?? "Other" }
        return grouped.sorted { $0.key < $1.key }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // MARK: - Hero Image
                heroImage

                // MARK: - Restaurant Info
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    actionButtons

                    Divider()

                    // Matched items section
                    if !restaurant.matchedItems.isEmpty {
                        matchedItemsSection
                        Divider()
                    }

                    // Full menu
                    fullMenuSection
                }
                .padding(.horizontal)
                .padding(.top, 20)
                .padding(.bottom, 40)
            }
        }
        .navigationTitle(restaurant.name)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadFullMenu()
        }
    }

    // MARK: - Hero Image

    private var heroImage: some View {
        ZStack(alignment: .bottomLeading) {
            if let firstPhoto = restaurant.photos.first,
               let url = URL(string: firstPhoto) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    case .failure:
                        heroPlaceholder
                    case .empty:
                        ZStack {
                            Color(.systemGray6)
                            ProgressView()
                        }
                    @unknown default:
                        heroPlaceholder
                    }
                }
            } else {
                heroPlaceholder
            }
        }
        .frame(height: 220)
        .clipped()
    }

    private var heroPlaceholder: some View {
        ZStack {
            LinearGradient(
                colors: [Color.accentColor.opacity(0.3), Color.accentColor.opacity(0.1)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Image(systemName: "fork.knife")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Header Section

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(restaurant.name)
                .font(.title2.weight(.bold))

            HStack(spacing: 12) {
                // Rating
                if let rating = restaurant.rating {
                    HStack(spacing: 4) {
                        ForEach(0..<5) { index in
                            starImage(for: index, rating: rating)
                                .font(.caption)
                                .foregroundStyle(.yellow)
                        }
                        Text(String(format: "%.1f", rating))
                            .font(.subheadline.weight(.medium))
                    }
                }

                // Price level
                if let price = restaurant.priceLevelString {
                    Text(price)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            // Address
            HStack(spacing: 6) {
                Image(systemName: "mappin.circle.fill")
                    .foregroundStyle(.red)
                    .font(.subheadline)
                Text(restaurant.address)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Distance
            if let distance = restaurant.distanceMiles {
                HStack(spacing: 6) {
                    Image(systemName: "location.fill")
                        .foregroundStyle(.blue)
                        .font(.subheadline)
                    Text(formattedDistance(distance))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Action Buttons

    private var actionButtons: some View {
        HStack(spacing: 12) {
            // Directions
            actionButton(
                title: "Directions",
                icon: "arrow.triangle.turn.up.right.diamond.fill",
                color: .blue
            ) {
                openInMaps()
            }

            // Call
            if let phone = restaurant.phone, !phone.isEmpty {
                actionButton(
                    title: "Call",
                    icon: "phone.fill",
                    color: .green
                ) {
                    callRestaurant(phone)
                }
            }

            // Website
            if let website = restaurant.websiteUrl,
               let url = URL(string: website) {
                actionButton(
                    title: "Website",
                    icon: "safari.fill",
                    color: .accentColor
                ) {
                    UIApplication.shared.open(url)
                }
            }
        }
    }

    private func actionButton(
        title: String,
        icon: String,
        color: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(color)

                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.primary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(color.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Matched Items Section

    private var matchedItemsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Matched Items", systemImage: "checkmark.seal.fill")
                .font(.headline)
                .foregroundStyle(.green)

            ForEach(restaurant.matchedItems) { item in
                MenuItemRow(item: item, isMatch: true)
            }
        }
    }

    // MARK: - Full Menu Section

    private var fullMenuSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Full Menu", systemImage: "menucard.fill")
                .font(.headline)

            if isLoadingMenu {
                HStack {
                    Spacer()
                    ProgressView("Loading menu...")
                    Spacer()
                }
                .padding(.vertical, 20)
            } else if fullMenu.isEmpty {
                ContentUnavailableView(
                    "No menu available",
                    systemImage: "menucard",
                    description: Text("Menu details are not available for this restaurant.")
                )
            } else {
                ForEach(menuByCategory, id: \.0) { category, items in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(category)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .padding(.top, 8)

                        ForEach(items) { item in
                            MenuItemRow(
                                item: item,
                                isMatch: matchedItemIds.contains(item.id)
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func starImage(for index: Int, rating: Double) -> Image {
        let threshold = Double(index) + 1
        if rating >= threshold {
            return Image(systemName: "star.fill")
        } else if rating >= threshold - 0.5 {
            return Image(systemName: "star.leadinghalf.filled")
        } else {
            return Image(systemName: "star")
        }
    }

    private func formattedDistance(_ miles: Double) -> String {
        if miles < 0.1 {
            return "Nearby"
        }
        return String(format: "%.1f miles away", miles)
    }

    private func openInMaps() {
        let coordinate = CLLocationCoordinate2D(
            latitude: restaurant.lat,
            longitude: restaurant.lng
        )
        let placemark = MKPlacemark(coordinate: coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = restaurant.name
        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving
        ])
    }

    private func callRestaurant(_ phone: String) {
        let cleaned = phone.replacingOccurrences(
            of: "[^0-9+]",
            with: "",
            options: .regularExpression
        )
        if let url = URL(string: "tel://\(cleaned)") {
            UIApplication.shared.open(url)
        }
    }

    private func loadFullMenu() async {
        isLoadingMenu = true
        do {
            let detail = try await APIClient.shared.getRestaurant(id: restaurant.id)
            fullMenu = detail.matchedItems // The detail endpoint returns the full menu in matchedItems
        } catch {
            // Fall back to showing only matched items
            fullMenu = restaurant.matchedItems
        }
        isLoadingMenu = false
    }
}

#Preview {
    NavigationStack {
        RestaurantDetailView(
            restaurant: Restaurant(
                id: UUID(),
                name: "Taco Palace",
                address: "123 Main St, San Francisco, CA 94102",
                lat: 37.7749,
                lng: -122.4194,
                websiteUrl: "https://example.com",
                phone: "+14155551234",
                rating: 4.5,
                priceLevel: 2,
                photos: [],
                distanceMiles: 0.4,
                matchedItems: [
                    MenuItem(id: UUID(), name: "Carne Asada Taco", description: "Grilled marinated steak with onions, cilantro, and salsa verde", price: 4.50, category: "Tacos"),
                    MenuItem(id: UUID(), name: "Fish Taco", description: "Beer battered cod with cabbage slaw", price: 5.00, category: "Tacos")
                ]
            ),
            searchQuery: "tacos"
        )
    }
}
