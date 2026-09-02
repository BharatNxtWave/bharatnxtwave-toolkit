(function () {
    "use strict";

    const drawer = document.getElementById("bde-quick-drawer");
    const overlay = document.getElementById("bde-quick-overlay");
    const drawerContent = document.getElementById("bde-quick-drawer-content");
    const closeButton = document.getElementById("bde-quick-close");

    const globalForm = document.querySelector(".bde-global-search");
    const globalInput = globalForm
        ? globalForm.querySelector('input[type="search"][name="q"]')
        : null;
    const globalShortcut = globalForm
        ? globalForm.querySelector(".search-shortcut")
        : null;

    let suggestionTimer = null;
    let suggestionController = null;
    let suggestionActiveIndex = -1;
    let suggestionBox = null;

    function escapeHtml(value) {
        return String(value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function safeUrl(value) {
        try {
            const url = new URL(value, window.location.origin);

            if (url.protocol === "http:" || url.protocol === "https:") {
                return url.href;
            }
        }
        catch (error) {
            return "";
        }

        return "";
    }

    function feedbackHost() {
        let host = document.getElementById("bde-live-feedback");

        if (!host) {
            host = document.createElement("div");
            host.id = "bde-live-feedback";
            host.className = "bde-live-feedback";
            host.setAttribute("aria-live", "polite");
            host.setAttribute("aria-atomic", "true");
            document.body.appendChild(host);
        }

        return host;
    }

    function notify(message, type, duration) {
        const host = feedbackHost();
        const toast = document.createElement("div");
        const mode = type || "info";
        const timeout = Number(duration || 2400);

        toast.className = "bde-live-toast " + mode;
        toast.innerHTML = `
            <span class="bde-live-toast-icon" aria-hidden="true">
                ${mode === "success" ? "✓" : mode === "error" ? "!" : mode === "warning" ? "!" : "i"}
            </span>
            <span>${escapeHtml(message)}</span>
        `;

        host.appendChild(toast);

        while (host.children.length > 3) {
            host.firstElementChild.remove();
        }

        window.setTimeout(function () {
            toast.classList.add("leaving");
            window.setTimeout(function () { toast.remove(); }, 180);
        }, timeout);
    }

    function paragraph(value) {
        const text = String(value || "").trim();

        if (!text) {
            return '<p class="bde-not-recorded">Not available in Toolkit.</p>';
        }

        return "<p>" + escapeHtml(text) + "</p>";
    }

    function sourceLinks(items) {
        if (!Array.isArray(items) || !items.length) {
            return '<p class="bde-not-recorded">No external scheme link is recorded.</p>';
        }

        return `
            <div class="bde-quick-links">
                ${items.map(function (item) {
                    const href = safeUrl(item.url);

                    if (!href) {
                        return "";
                    }

                    return `
                        <a href="${escapeHtml(href)}"
                           target="_blank"
                           rel="noopener noreferrer"
                           class="bde-feedback-external">
                            <span>${escapeHtml(item.label || item.name || "External Link")}</span>
                            <b>↗</b>
                        </a>
                    `;
                }).join("")}
            </div>
        `;
    }

    function serviceMarkup(data) {
        const primary = safeUrl(data.primary_url);
        const detail = safeUrl(data.detail_url);

        return `
            <div class="bde-preview-ready"><span></span> Details loaded</div>
            <div class="bde-preview-kicker">QUICK DETAILS</div>
            <div class="bde-preview-code">${escapeHtml(data.service_id)}</div>
            <h2 class="bde-quick-title">${escapeHtml(data.title)}</h2>

            <div class="bde-preview-tags">
                <span>${escapeHtml(data.kind)}</span>
                <span>${escapeHtml(data.category)}</span>
            </div>

            <div class="bde-preview-fact-grid">
                <div>
                    <span>Deadline</span>
                    <strong>${escapeHtml(data.deadline || "Not recorded")}</strong>
                </div>
                <div>
                    <span>Pitch status</span>
                    <strong>${escapeHtml(data.pitch_state || "—")}</strong>
                </div>
            </div>

            ${data.summary ? `
                <div class="bde-quick-block">
                    <span>WHAT IT DOES</span>
                    <div class="bde-quick-summary">${escapeHtml(data.summary)}</div>
                </div>
            ` : ""}

            <div class="bde-quick-block">
                <span>ELIGIBILITY</span>
                ${paragraph(data.eligibility || data.applicable_for)}
            </div>

            <div class="bde-quick-block">
                <span>BENEFITS</span>
                ${paragraph(data.benefits)}
            </div>

            ${data.funding_organisation ? `
                <div class="bde-quick-block">
                    <span>RUN BY</span>
                    <p>${escapeHtml(data.funding_organisation)}</p>
                </div>
            ` : ""}

            <div class="bde-quick-block">
                <span>SCHEME LINKS</span>
                ${sourceLinks(data.sources)}
            </div>

            <div class="bde-quick-footer">
                ${primary ? `
                    <a href="${escapeHtml(primary)}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="bde-external-button bde-feedback-external">
                        Open Scheme ↗
                    </a>
                ` : ""}

                ${detail ? `
                    <a href="${escapeHtml(detail)}"
                       class="primary-button">
                        Full Details
                    </a>
                ` : ""}
            </div>
        `;
    }

    function loadingMarkup(label) {
        return `
            <div class="bde-quick-loading bde-skeleton-wrap" aria-live="polite">
                <span class="bde-mini-spinner"></span>
                <strong>${escapeHtml(label || "Loading service…")}</strong>
                <div class="bde-skeleton-line wide"></div>
                <div class="bde-skeleton-line"></div>
                <div class="bde-skeleton-line short"></div>
            </div>
        `;
    }

    async function loadService(serviceId, searchQuery) {
        const searchSuffix = searchQuery
            ? "?search_q=" + encodeURIComponent(searchQuery)
            : "";
        const response = await fetch(
            "/toolkit/library/quick/" + encodeURIComponent(serviceId) + "/" + searchSuffix,
            {
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            }
        );

        if (!response.ok) {
            throw new Error("Quick view request failed");
        }

        return response.json();
    }

    function openDrawer() {
        if (!drawer || !overlay) {
            return;
        }

        drawer.hidden = false;
        overlay.hidden = false;
        document.body.style.overflow = "hidden";
    }

    function closeDrawer() {
        if (!drawer || !overlay) {
            return;
        }

        drawer.hidden = true;
        overlay.hidden = true;
        document.body.style.overflow = "";
    }

    async function showInDrawer(serviceId, searchQuery) {
        if (!drawerContent) {
            return;
        }

        openDrawer();
        drawerContent.innerHTML = loadingMarkup("Loading service details…");

        try {
            const data = await loadService(serviceId, searchQuery);
            drawerContent.innerHTML = serviceMarkup(data);
            notify("Service details ready", "success", 1600);
        }
        catch (error) {
            drawerContent.innerHTML = `
                <div class="bde-empty-state compact">
                    <h3>Could not load this service</h3>
                    <p>Please open the full service page and try again.</p>
                </div>
            `;
            notify("Could not load service details", "error", 4200);
        }
    }

    async function showInLibrary(serviceId, button, searchQuery) {
        const target = document.getElementById("bde-library-preview");

        if (!target) {
            return;
        }

        document.querySelectorAll(".bde-library-row.active").forEach(function (item) {
            item.classList.remove("active");
        });

        if (button) {
            button.classList.add("active");
            button.setAttribute("aria-busy", "true");
        }

        target.innerHTML = loadingMarkup("Loading service details…");

        try {
            const data = await loadService(serviceId, searchQuery);
            target.innerHTML = serviceMarkup(data);
        }
        catch (error) {
            target.innerHTML = `
                <div class="bde-empty-state compact">
                    <h3>Could not load service details</h3>
                    <p>Use the full details page instead.</p>
                </div>
            `;
            notify("Could not load Service Library preview", "error", 4200);
        }
        finally {
            if (button) {
                button.removeAttribute("aria-busy");
            }
        }
    }

    function initGlobalSearch() {
        if (!globalForm || !globalInput) {
            return;
        }

        const libraryMode = window.location.pathname.startsWith("/toolkit/library/");
        globalForm.action = libraryMode ? "/toolkit/library/" : "/toolkit/";
        globalForm.classList.add("bde-smart-search");
        globalInput.id = "bde-global-search-input";
        globalInput.placeholder = libraryMode
            ? "Search all 163 published services…"
            : "Search services, schemes, sectors or client needs…";

        const currentQuery = new URLSearchParams(window.location.search).get("q");
        if (currentQuery !== null) {
            globalInput.value = currentQuery;
        }

        if (globalShortcut) {
            globalShortcut.textContent = "Ctrl K";
            globalShortcut.setAttribute("aria-hidden", "true");
        }

        suggestionBox = document.createElement("div");
        suggestionBox.id = "bde-global-suggestions";
        suggestionBox.className = "bde-global-suggestions";
        suggestionBox.hidden = true;
        globalForm.appendChild(suggestionBox);

        function items() {
            return Array.from(suggestionBox.querySelectorAll(".bde-smart-suggestion"));
        }

        function setActive(index) {
            const list = items();
            list.forEach(function (item) { item.classList.remove("active"); });

            if (!list.length) {
                suggestionActiveIndex = -1;
                return;
            }

            suggestionActiveIndex = Math.max(0, Math.min(index, list.length - 1));
            const active = list[suggestionActiveIndex];
            active.classList.add("active");
            active.scrollIntoView({ block: "nearest" });
        }

        function closeSuggestions() {
            suggestionActiveIndex = -1;
            suggestionBox.hidden = true;
            suggestionBox.innerHTML = "";
        }

        function renderLoading() {
            suggestionBox.innerHTML = `
                <div class="bde-suggestion-state">
                    <span class="bde-mini-spinner"></span>
                    Finding services…
                </div>
            `;
            suggestionBox.hidden = false;
        }

        function renderSuggestions(results) {
            suggestionActiveIndex = -1;

            if (!Array.isArray(results) || !results.length) {
                suggestionBox.innerHTML = `
                    <div class="bde-suggestion-state empty">
                        <strong>No quick recommendation</strong>
                        <span>Press Enter to run the full catalog search.</span>
                    </div>
                `;
                suggestionBox.hidden = false;
                return;
            }

            suggestionBox.innerHTML = results.map(function (item) {
                return `
                    <button type="button"
                            class="bde-smart-suggestion"
                            data-service-id="${Number(item.pk) || 0}"
                            data-service-title="${escapeHtml(item.title)}">
                        <span class="bde-suggestion-main">
                            <strong>${escapeHtml(item.title)}</strong>
                            <small>${escapeHtml(item.kind)} · ${escapeHtml(item.category)}</small>
                        </span>
                        <span class="bde-suggestion-side">
                            <small>${escapeHtml(item.deadline || "")}</small>
                            <b>Quick View</b>
                        </span>
                    </button>
                `;
            }).join("");
            suggestionBox.hidden = false;
        }

        async function requestSuggestions(query) {
            if (suggestionController) {
                suggestionController.abort();
            }

            suggestionController = new AbortController();
            renderLoading();

            try {
                const response = await fetch(
                    "/toolkit/search/suggestions/?q=" + encodeURIComponent(query),
                    {
                        credentials: "same-origin",
                        signal: suggestionController.signal,
                        headers: { "X-Requested-With": "XMLHttpRequest" }
                    }
                );

                if (!response.ok) {
                    throw new Error("Suggestion request failed");
                }

                const data = await response.json();
                renderSuggestions(data.results || []);
            }
            catch (error) {
                if (error.name === "AbortError") {
                    return;
                }

                suggestionBox.innerHTML = `
                    <div class="bde-suggestion-state warning">
                        <strong>Recommendations unavailable</strong>
                        <span>Press Enter — full search still works.</span>
                    </div>
                `;
                suggestionBox.hidden = false;
            }
        }

        globalInput.addEventListener("input", function () {
            window.clearTimeout(suggestionTimer);
            const query = globalInput.value.trim();

            if (query.length < 2) {
                closeSuggestions();
                return;
            }

            suggestionTimer = window.setTimeout(function () {
                requestSuggestions(query);
            }, 60);
        });

        globalInput.addEventListener("focus", function () {
            if (globalInput.value.trim().length >= 2 && suggestionBox.innerHTML.trim()) {
                suggestionBox.hidden = false;
            }
        });

        globalInput.addEventListener("keydown", function (event) {
            const list = items();

            if (event.key === "ArrowDown" && list.length) {
                event.preventDefault();
                setActive(suggestionActiveIndex < 0 ? 0 : suggestionActiveIndex + 1);
                return;
            }

            if (event.key === "ArrowUp" && list.length) {
                event.preventDefault();
                setActive(suggestionActiveIndex < 0 ? list.length - 1 : suggestionActiveIndex - 1);
                return;
            }

            if (event.key === "Enter" && suggestionActiveIndex >= 0 && list[suggestionActiveIndex]) {
                event.preventDefault();
                list[suggestionActiveIndex].click();
                return;
            }

            if (event.key === "Escape") {
                closeSuggestions();
            }
        });

        suggestionBox.addEventListener("click", function (event) {
            const item = event.target.closest(".bde-smart-suggestion");

            if (!item) {
                return;
            }

            const serviceId = item.dataset.serviceId;
            const title = item.dataset.serviceTitle || "Service";
            const searchQuery = globalInput.value.trim();

            globalInput.value = title;
            closeSuggestions();
            notify("Opening quick view", "info", 1100);
            showInDrawer(serviceId, searchQuery);
        });

        globalForm.addEventListener("submit", function () {
            const query = globalInput.value.trim();
            closeSuggestions();

            if (query) {
                globalForm.setAttribute("aria-busy", "true");
                if (globalShortcut) {
                    globalShortcut.textContent = "Searching…";
                }
            }
        });

        document.addEventListener("click", function (event) {
            if (!globalForm.contains(event.target)) {
                closeSuggestions();
            }
        });
    }


    /* BDE_PAGE_SEARCH_V13 */

    function initPageSearch() {

        const forms = Array.from(
            document.querySelectorAll(
                ".bde-page-search"
            )
        );

        if (!forms.length) {
            return;
        }

        forms.forEach(function (form) {

            const input =
                form.querySelector(
                    'input[type="search"][name="q"]'
                );

            const suggestions =
                form.querySelector(
                    ".bde-page-suggestions"
                );

            if (!input || !suggestions) {
                return;
            }

            let timer = null;
            let controller = null;
            let activeIndex = -1;


            function suggestionItems() {
                return Array.from(
                    suggestions.querySelectorAll(
                        ".bde-smart-suggestion"
                    )
                );
            }


            function closeSuggestions() {
                suggestions.hidden = true;
                suggestions.innerHTML = "";
                activeIndex = -1;
            }


            function setActive(index) {

                const items = suggestionItems();

                items.forEach(function (item) {
                    item.classList.remove("active");
                });

                if (!items.length) {
                    activeIndex = -1;
                    return;
                }

                activeIndex = Math.max(
                    0,
                    Math.min(
                        index,
                        items.length - 1
                    )
                );

                items[activeIndex]
                    .classList.add("active");

                items[activeIndex]
                    .scrollIntoView({
                        block: "nearest"
                    });
            }


            function renderLoading() {

                suggestions.innerHTML = `
                    <div class="bde-suggestion-state">
                        <span class="bde-mini-spinner"></span>
                        Finding the best matching services…
                    </div>
                `;

                suggestions.hidden = false;
            }


            function renderResults(results) {

                activeIndex = -1;

                if (
                    !Array.isArray(results)
                    ||
                    !results.length
                ) {

                    suggestions.innerHTML = `
                        <div class="bde-suggestion-state empty">
                            <strong>No instant recommendation</strong>
                            <span>
                                Press Enter to run a complete search.
                            </span>
                        </div>
                    `;

                    suggestions.hidden = false;
                    return;
                }


                suggestions.innerHTML =
                    results.map(function (item) {

                        return `
                            <button
                                type="button"
                                class="bde-smart-suggestion"
                                data-service-id="${Number(item.pk) || 0}"
                                data-service-title="${escapeHtml(item.title)}">

                                <span class="bde-suggestion-main">

                                    <strong>
                                        ${escapeHtml(item.title)}
                                    </strong>

                                    <small>
                                        ${escapeHtml(item.kind)}
                                        ·
                                        ${escapeHtml(item.category)}
                                    </small>

                                </span>

                                <span class="bde-suggestion-side">

                                    <small>
                                        ${escapeHtml(item.deadline || "")}
                                    </small>

                                    <b>
                                        Quick View →
                                    </b>

                                </span>

                            </button>
                        `;
                    }).join("");

                suggestions.hidden = false;
            }


            async function fetchSuggestions(query) {

                if (controller) {
                    controller.abort();
                }

                controller =
                    new AbortController();

                renderLoading();

                try {

                    const response =
                        await fetch(
                            "/toolkit/search/suggestions/?q="
                            + encodeURIComponent(query),
                            {
                                credentials:
                                    "same-origin",

                                signal:
                                    controller.signal,

                                headers: {
                                    "X-Requested-With":
                                        "XMLHttpRequest"
                                }
                            }
                        );


                    if (!response.ok) {
                        throw new Error(
                            "Suggestion request failed"
                        );
                    }


                    const data =
                        await response.json();

                    renderResults(
                        data.results || []
                    );

                }
                catch (error) {

                    if (
                        error.name ===
                        "AbortError"
                    ) {
                        return;
                    }

                    suggestions.innerHTML = `
                        <div class="bde-suggestion-state warning">
                            <strong>
                                Recommendations unavailable
                            </strong>
                            <span>
                                Press Enter — normal search still works.
                            </span>
                        </div>
                    `;

                    suggestions.hidden = false;
                }
            }


            input.addEventListener(
                "input",
                function () {

                    window.clearTimeout(timer);

                    const query =
                        input.value.trim();

                    if (query.length < 2) {
                        closeSuggestions();
                        return;
                    }

                    timer =
                        window.setTimeout(
                            function () {
                                fetchSuggestions(query);
                            },
                            180
                        );
                }
            );


            input.addEventListener(
                "keydown",
                function (event) {

                    const items =
                        suggestionItems();


                    if (
                        event.key === "ArrowDown"
                        &&
                        items.length
                    ) {

                        event.preventDefault();

                        setActive(
                            activeIndex < 0
                                ? 0
                                : activeIndex + 1
                        );

                        return;
                    }


                    if (
                        event.key === "ArrowUp"
                        &&
                        items.length
                    ) {

                        event.preventDefault();

                        setActive(
                            activeIndex < 0
                                ? items.length - 1
                                : activeIndex - 1
                        );

                        return;
                    }


                    if (
                        event.key === "Enter"
                        &&
                        activeIndex >= 0
                        &&
                        items[activeIndex]
                    ) {

                        event.preventDefault();

                        items[
                            activeIndex
                        ].click();

                        return;
                    }


                    if (
                        event.key === "Escape"
                    ) {

                        closeSuggestions();
                    }
                }
            );


            suggestions.addEventListener(
                "click",
                function (event) {

                    const item =
                        event.target.closest(
                            ".bde-smart-suggestion"
                        );

                    if (!item) {
                        return;
                    }


                    const serviceId =
                        item.dataset.serviceId;

                    const title =
                        item.dataset.serviceTitle
                        || "Service";

                    const searchQuery =
                        input.value.trim();


                    input.value =
                        title;

                    closeSuggestions();


                    if (
                        form.dataset.searchContext
                        === "library"
                    ) {

                        notify(
                            "Opening service preview…",
                            "info",
                            1200
                        );

                        showInLibrary(
                            serviceId,
                            null,
                            searchQuery
                        );
                    }

                    else {

                        notify(
                            "Opening quick view…",
                            "info",
                            1200
                        );

                        showInDrawer(
                            serviceId,
                            searchQuery
                        );
                    }
                }
            );


            document.addEventListener(
                "click",
                function (event) {

                    if (
                        !form.contains(
                            event.target
                        )
                    ) {
                        closeSuggestions();
                    }
                }
            );

        });
    }


    initGlobalSearch();
    initPageSearch();

    document.addEventListener("click", function (event) {
        const trigger = event.target.closest("[data-service-quick]");

        if (trigger) {
            event.preventDefault();
            const serviceId = trigger.dataset.serviceQuick;

            if (!serviceId) {
                return;
            }

            if (trigger.dataset.quickMode === "library") {
                showInLibrary(serviceId, trigger);
            }
            else {
                showInDrawer(serviceId);
            }
            return;
        }

        const external = event.target.closest('a[target="_blank"]');
        if (external && external.href) {
            notify("Opening scheme in a new tab", "info", 1800);
        }
    });

    if (closeButton) {
        closeButton.addEventListener("click", closeDrawer);
    }

    if (overlay) {
        overlay.addEventListener("click", closeDrawer);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && drawer && !drawer.hidden) {
            closeDrawer();
        }

        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {

            event.preventDefault();

            const pageInput =
                document.querySelector(
                    '.bde-page-search input[type="search"][name="q"]'
                );

            if (pageInput) {

                pageInput.focus();
                pageInput.select();

                notify(
                    "Search ready",
                    "info",
                    900
                );
            }

            else if (globalInput) {

                globalInput.focus();
                globalInput.select();
            }
        }
    });

    document.querySelectorAll(".bde-auto-submit").forEach(function (control) {
        control.addEventListener("change", function () {
            const form = control.form;
            if (!form) {
                return;
            }
            notify(form.dataset.feedbackMessage || "Updating view…", "info", 1200);
            form.submit();
        });
    });

    document.addEventListener("submit", function (event) {
        const feedbackForm = event.target.closest(".bde-feedback-form");
        if (feedbackForm && !event.defaultPrevented) {
            notify(feedbackForm.dataset.feedbackMessage || "Updating view…", "info", 1200);

            const button = feedbackForm.querySelector('button[type="submit"]');
            if (button && !button.disabled) {
                button.dataset.originalText = button.textContent;
                button.textContent = "Working…";
                button.disabled = true;
            }
        }

        const matcherForm = event.target.closest("#client-match-form form");
        if (matcherForm && !event.defaultPrevented) {
            notify("Checking the client against Toolkit services…", "info", 1800);
        }
    });

    document.addEventListener("submit", async function (event) {
        const form = event.target.closest(".bde-ajax-save");

        if (!form) {
            return;
        }

        event.preventDefault();

        const button = form.querySelector("button[type='submit']");

        if (!button || button.disabled) {
            return;
        }

        const originalText = button.textContent;
        const iconMode = button.classList.contains("bde-save-icon");
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.textContent = iconMode ? "…" : "Saving…";

        try {
            const response = await fetch(
                form.action,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                    body: new FormData(form)
                }
            );

            if (!response.ok) {
                throw new Error("Save request failed");
            }

            const data = await response.json();

            if (iconMode) {
                button.innerHTML = data.saved ? '<span class="bn-bookmark-icon is-saved" aria-hidden="true"></span>' : '<span class="bn-bookmark-icon" aria-hidden="true"></span>';
            }
            else {
                button.innerHTML = data.saved ? '<span class="bn-bookmark-icon is-saved" aria-hidden="true"></span><span>Saved</span>' : '<span class="bn-bookmark-icon" aria-hidden="true"></span><span>Save</span>';
            }

            button.classList.toggle("saved", Boolean(data.saved));
            notify(
                data.saved ? "Saved for quick access" : "Removed from Saved Services",
                "success",
                2200
            );
        }
        catch (error) {
            button.textContent = originalText;
            notify("Could not update Saved Services. Please try again.", "error", 4200);
        }
        finally {
            button.disabled = false;
            button.removeAttribute("aria-busy");
        }
    });
})();
