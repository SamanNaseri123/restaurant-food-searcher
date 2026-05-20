import SwiftUI

struct SearchBar: View {
    @Binding var text: String
    @Bindable var searchViewModel: SearchViewModel
    var onSubmit: () -> Void
    var onSuggestionSelected: (String) -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // MARK: - Search Field
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                    .font(.body.weight(.medium))

                TextField("Search for a dish...", text: $text)
                    .textFieldStyle(.plain)
                    .font(.body)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .focused($isFocused)
                    .submitLabel(.search)
                    .onSubmit {
                        isFocused = false
                        onSubmit()
                    }
                    .onChange(of: text) { _, newValue in
                        searchViewModel.onQueryChanged(newValue)
                    }

                if !text.isEmpty {
                    Button {
                        text = ""
                        searchViewModel.clearSuggestions()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(.ultraThickMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .shadow(color: .black.opacity(0.1), radius: 8, y: 4)

            // MARK: - Autocomplete Suggestions
            if isFocused && !searchViewModel.suggestions.isEmpty {
                suggestionsDropdown
            }
        }
    }

    // MARK: - Suggestions Dropdown

    private var suggestionsDropdown: some View {
        VStack(spacing: 0) {
            ForEach(searchViewModel.suggestions, id: \.self) { suggestion in
                Button {
                    text = suggestion
                    isFocused = false
                    searchViewModel.clearSuggestions()
                    onSuggestionSelected(suggestion)
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(.tertiary)
                            .font(.subheadline)

                        Text(suggestion)
                            .font(.body)
                            .foregroundStyle(.primary)

                        Spacer()

                        Image(systemName: "arrow.up.left")
                            .foregroundStyle(.tertiary)
                            .font(.caption)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                }

                if suggestion != searchViewModel.suggestions.last {
                    Divider()
                        .padding(.leading, 40)
                }
            }
        }
        .background(.ultraThickMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.08), radius: 6, y: 4)
        .padding(.top, 4)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}

#Preview {
    VStack {
        SearchBar(
            text: .constant("tacos"),
            searchViewModel: SearchViewModel(),
            onSubmit: {},
            onSuggestionSelected: { _ in }
        )
        Spacer()
    }
    .padding()
}
