import Foundation

@Observable
final class SearchViewModel {
    var suggestions: [String] = []
    var isLoadingSuggestions: Bool = false

    private let apiClient = APIClient.shared
    private var debounceTask: Task<Void, Never>?

    /// Called when the search query text changes; debounces and fetches suggestions
    func onQueryChanged(_ query: String) {
        // Cancel any pending debounce
        debounceTask?.cancel()

        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)

        // Need at least 2 characters
        guard trimmed.count >= 2 else {
            suggestions = []
            return
        }

        // Debounce 300ms
        debounceTask = Task { @MainActor in
            do {
                try await Task.sleep(for: .milliseconds(300))
            } catch {
                return // Cancelled
            }

            guard !Task.isCancelled else { return }
            await fetchSuggestions(query: trimmed)
        }
    }

    /// Clear all suggestions
    func clearSuggestions() {
        debounceTask?.cancel()
        suggestions = []
    }

    // MARK: - Private

    private func fetchSuggestions(query: String) async {
        isLoadingSuggestions = true

        do {
            let results = try await apiClient.autocomplete(query: query)
            if !Task.isCancelled {
                suggestions = results
            }
        } catch {
            if !Task.isCancelled {
                suggestions = []
            }
        }

        isLoadingSuggestions = false
    }
}
