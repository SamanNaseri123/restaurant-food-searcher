import SwiftUI

struct MenuItemRow: View {
    let item: MenuItem
    let isMatch: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Match indicator
            if isMatch {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.body)
                    .padding(.top, 2)
            }

            // Item info
            VStack(alignment: .leading, spacing: 4) {
                Text(item.name)
                    .font(.body.weight(isMatch ? .semibold : .regular))
                    .foregroundStyle(isMatch ? .green : .primary)

                if let description = item.description, !description.isEmpty {
                    Text(description)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 8)

            // Price
            if let price = item.formattedPrice {
                Text(price)
                    .font(.body.weight(.medium))
                    .foregroundStyle(isMatch ? .green : .primary)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            isMatch
            ? Color.green.opacity(0.08)
            : Color.clear
        )
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

#Preview {
    VStack(spacing: 8) {
        MenuItemRow(
            item: MenuItem(
                id: UUID(),
                name: "Carne Asada Taco",
                description: "Grilled marinated steak with onions and cilantro",
                price: 4.50,
                category: "Tacos"
            ),
            isMatch: true
        )

        MenuItemRow(
            item: MenuItem(
                id: UUID(),
                name: "Chips & Guacamole",
                description: "House-made tortilla chips with fresh guacamole",
                price: 8.00,
                category: "Appetizers"
            ),
            isMatch: false
        )
    }
    .padding()
}
