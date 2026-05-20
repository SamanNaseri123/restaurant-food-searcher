import SwiftUI

struct RestaurantCardView: View {
    let restaurant: Restaurant
    let searchQuery: String

    var body: some View {
        HStack(spacing: 14) {
            // MARK: - Photo
            restaurantPhoto

            // MARK: - Info
            VStack(alignment: .leading, spacing: 6) {
                // Name
                Text(restaurant.name)
                    .font(.headline)
                    .lineLimit(1)

                // Rating + Price + Distance
                HStack(spacing: 8) {
                    if let rating = restaurant.rating {
                        ratingView(rating)
                    }

                    if let price = restaurant.priceLevelString {
                        Text(price)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    if let distance = restaurant.distanceMeters {
                        Text(formattedDistance(distance))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                // Matched items as chips
                if !restaurant.matchedItems.isEmpty {
                    matchedItemsView
                }
            }

            Spacer(minLength: 0)

            // Chevron
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .padding(14)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
    }

    // MARK: - Restaurant Photo

    private var restaurantPhoto: some View {
        Group {
            if let firstPhoto = restaurant.photos.first,
               let url = URL(string: firstPhoto) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    case .failure:
                        photoPlaceholder
                    case .empty:
                        ProgressView()
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(Color(.systemGray6))
                    @unknown default:
                        photoPlaceholder
                    }
                }
            } else {
                photoPlaceholder
            }
        }
        .frame(width: 72, height: 72)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var photoPlaceholder: some View {
        ZStack {
            Color(.systemGray6)
            Image(systemName: "fork.knife")
                .font(.title2)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Rating

    private func ratingView(_ rating: Double) -> some View {
        HStack(spacing: 2) {
            Image(systemName: "star.fill")
                .font(.caption2)
                .foregroundStyle(.yellow)
            Text(String(format: "%.1f", rating))
                .font(.subheadline.weight(.medium))
        }
    }

    // MARK: - Matched Items

    private var matchedItemsView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(restaurant.matchedItems.prefix(4)) { item in
                    Text(item.name)
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.green.opacity(0.15))
                        .foregroundStyle(.green)
                        .clipShape(Capsule())
                }

                if restaurant.matchedItems.count > 4 {
                    Text("+\(restaurant.matchedItems.count - 4)")
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(.systemGray5))
                        .foregroundStyle(.secondary)
                        .clipShape(Capsule())
                }
            }
        }
    }

    // MARK: - Helpers

    private func formattedDistance(_ meters: Double) -> String {
        if meters < 1000 {
            return "\(Int(meters))m"
        } else {
            let miles = meters / 1609.34
            return String(format: "%.1f mi", miles)
        }
    }
}

#Preview {
    RestaurantCardView(
        restaurant: Restaurant(
            id: UUID(),
            name: "Taco Palace",
            address: "123 Main St, San Francisco, CA",
            lat: 37.7749,
            lng: -122.4194,
            websiteUrl: "https://example.com",
            phone: "+14155551234",
            rating: 4.5,
            priceLevel: 2,
            photos: [],
            distanceMeters: 850,
            matchedItems: [
                MenuItem(id: UUID(), name: "Carne Asada Taco", description: "Grilled steak", price: 4.50, category: "Tacos"),
                MenuItem(id: UUID(), name: "Fish Taco", description: "Beer battered", price: 5.00, category: "Tacos")
            ]
        ),
        searchQuery: "tacos"
    )
    .padding()
}
