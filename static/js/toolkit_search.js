(function () {
    "use strict";

    const input = document.getElementById("toolkit-search-input");
    const suggestions = document.getElementById("toolkit-suggestions");

    if (!input || !suggestions) {
        return;
    }

    let timer = null;
    let controller = null;

    function hideSuggestions() {
        suggestions.hidden = true;
        suggestions.innerHTML = "";
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function renderResults(results) {
        if (!results.length) {
            suggestions.innerHTML = `
                <div class="toolkit-suggestion-empty">
                    No matching services
                </div>
            `;

            suggestions.hidden = false;
            return;
        }

        suggestions.innerHTML = results.map(function (item) {
            return `
                <a class="toolkit-suggestion"
                   href="${item.url}">

                    <div class="toolkit-suggestion-main">

                        <div class="toolkit-suggestion-title">
                            ${escapeHtml(item.title)}
                        </div>

                        <div class="toolkit-suggestion-path">
                            ${escapeHtml(item.domain)}
                            ·
                            ${escapeHtml(item.category)}
                        </div>

                    </div>

                    <div class="toolkit-suggestion-meta">
                        ${escapeHtml(item.service_id)}
                    </div>

                </a>
            `;
        }).join("");

        suggestions.hidden = false;
    }

    input.addEventListener("input", function () {
        clearTimeout(timer);

        const query = input.value.trim();

        if (query.length < 2) {
            hideSuggestions();
            return;
        }

        timer = setTimeout(function () {
            if (controller) {
                controller.abort();
            }

            controller = new AbortController();

            fetch(
                "/toolkit/search/suggestions/?q=" +
                encodeURIComponent(query),
                {
                    credentials: "same-origin",
                    signal: controller.signal
                }
            )
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Search request failed");
                }

                return response.json();
            })
            .then(function (data) {
                renderResults(data.results || []);
            })
            .catch(function (error) {
                if (error.name !== "AbortError") {
                    hideSuggestions();
                }
            });

        }, 60);
    });


    document.addEventListener("click", function (event) {
        if (
            !suggestions.contains(event.target)
            && event.target !== input
        ) {
            hideSuggestions();
        }
    });


    input.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            hideSuggestions();
        }
    });

})();
