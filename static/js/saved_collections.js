(function () {

    "use strict";


    const SAVE_ACTION_PATTERN =
        /\/toolkit\/service\/(\d+)\/save\/?$/;


    let modal = null;
    let currentServiceId = null;


    function csrfToken() {

        const input =
            document.querySelector(
                'input[name="csrfmiddlewaretoken"]'
            );


        if (input) {
            return input.value;
        }


        const cookies =
            document.cookie
                ? document.cookie.split(";")
                : [];


        for (const cookie of cookies) {

            const value = cookie.trim();

            if (
                value.startsWith(
                    "csrftoken="
                )
            ) {

                return decodeURIComponent(
                    value.substring(
                        "csrftoken=".length
                    )
                );

            }

        }


        return "";

    }


    function escapeHtml(value) {

        const element =
            document.createElement(
                "div"
            );


        element.textContent =
            value || "";


        return element.innerHTML;

    }


    function ensureModal() {

        if (modal) {
            return modal;
        }


        modal =
            document.createElement(
                "div"
            );


        modal.className =
            "bnx-save-collection-modal";


        modal.hidden = true;


        modal.innerHTML = `
            <div
                class="bnx-modal-backdrop"
                data-close-save-collections>
            </div>

            <div
                class="bnx-save-collection-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="bnx-save-collection-title">

                <div class="bnx-modal-handle"></div>

                <header>

                    <div>

                        <small>
                            SAVE SERVICE
                        </small>

                        <h2 id="bnx-save-collection-title">
                            Save to client
                        </h2>

                        <p
                            class="bnx-save-service-name"
                            data-save-service-name>
                        </p>

                    </div>

                    <button
                        type="button"
                        class="bnx-modal-close"
                        data-close-save-collections>
                        ×
                    </button>

                </header>


                <div
                    class="bnx-save-collection-content"
                    data-save-collection-content>

                    <div class="bnx-modal-loading">
                        Loading collections…
                    </div>

                </div>

            </div>
        `;


        document.body.appendChild(
            modal
        );


        modal
            .querySelectorAll(
                "[data-close-save-collections]"
            )
            .forEach(
                function (element) {

                    element.addEventListener(
                        "click",
                        closeModal
                    );

                }
            );


        return modal;

    }


    function closeModal() {

        if (!modal) {
            return;
        }


        modal.hidden = true;

        document.body.classList.remove(
            "bnx-modal-open"
        );


        currentServiceId = null;

    }


    async function loadCollections(
        serviceId
    ) {

        const response =
            await fetch(
                "/toolkit/service/"
                + serviceId
                + "/collections/",
                {
                    credentials:
                        "same-origin",
                }
            );


        if (!response.ok) {

            throw new Error(
                "Could not load collections."
            );

        }


        return response.json();

    }


    function collectionRow(
        collection
    ) {

        return `
            <button
                type="button"
                class="bnx-save-collection-row ${
                    collection.selected
                        ? "selected"
                        : ""
                }"
                data-toggle-collection="${
                    collection.id
                }">

                <div
                    class="bnx-save-collection-avatar">

                    ${
                        escapeHtml(
                            collection.name
                                .slice(
                                    0,
                                    1
                                )
                                .toUpperCase()
                        )
                    }

                </div>


                <div
                    class="bnx-save-collection-name">

                    <strong>
                        ${
                            escapeHtml(
                                collection.name
                            )
                        }
                    </strong>

                    <span>
                        ${
                            collection.note
                                ? escapeHtml(
                                    collection.note
                                )
                                : "Client collection"
                        }
                    </span>

                </div>


                <span
                    class="bnx-save-collection-check">

                    ${
                        collection.selected
                            ? "✓"
                            : "+"
                    }

                </span>

            </button>
        `;

    }


    function renderState(
        data
    ) {

        const name =
            modal.querySelector(
                "[data-save-service-name]"
            );


        const content =
            modal.querySelector(
                "[data-save-collection-content]"
            );


        name.textContent =
            data.service.title;


        let collections = "";


        if (data.collections.length) {

            collections =
                data.collections
                    .map(
                        collectionRow
                    )
                    .join("");

        }

        else {

            collections = `
                <div class="bnx-no-collections">
                    No client collections yet.
                    Create one below.
                </div>
            `;

        }


        content.innerHTML = `
            <div class="bnx-save-collections-heading">
                Client collections
            </div>

            <div class="bnx-save-collection-list">
                ${collections}
            </div>


            <button
                type="button"
                class="bnx-create-inline-collection"
                data-create-inline-collection>

                <span>+</span>

                Create new client collection

            </button>


            <form
                class="bnx-inline-collection-form"
                data-inline-collection-form
                hidden>

                <label>
                    Client / collection name

                    <input
                        type="text"
                        name="name"
                        maxlength="150"
                        placeholder="e.g. Deepak"
                        required>
                </label>

                <label>
                    Note
                    <small>Optional</small>

                    <input
                        type="text"
                        name="note"
                        maxlength="500"
                        placeholder="e.g. Agriculture business">
                </label>

                <div class="bnx-inline-actions">

                    <button
                        type="button"
                        class="secondary-button"
                        data-cancel-inline>
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="primary-button">
                        Create & save
                    </button>

                </div>

            </form>


            ${
                data.saved
                    ? `
                        <div class="bnx-save-modal-divider"></div>

                        <button
                            type="button"
                            class="bnx-remove-entire-save"
                            data-remove-entire-save>

                            Remove from Saved Services

                        </button>
                    `
                    : ""
            }
        `;


        bindModalActions();

    }


    async function postAction(
        params
    ) {

        const body =
            new URLSearchParams(
                params
            );


        const response =
            await fetch(
                "/toolkit/service/"
                + currentServiceId
                + "/collections/action/",
                {
                    method: "POST",

                    credentials:
                        "same-origin",

                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded",

                        "X-CSRFToken":
                            csrfToken(),

                        "X-Requested-With":
                            "XMLHttpRequest",
                    },

                    body:
                        body.toString(),
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error
                || "Could not update saved service."
            );

        }


        return data;

    }


    function updateBookmarkButtons(
        serviceId,
        saved
    ) {

        document
            .querySelectorAll(
                'form[action*="/toolkit/service/'
                + serviceId
                + '/save/"]'
            )
            .forEach(
                function (form) {

                    const button =
                        form.querySelector(
                            "button"
                        );


                    if (!button) {
                        return;
                    }


                    button.classList.toggle(
                        "saved",
                        saved
                    );


                    const icon =
                        button.querySelector(
                            ".bnx-bookmark-icon"
                        );


                    if (icon) {

                        icon.classList.toggle(
                            "is-saved",
                            saved
                        );

                    }


                    button.setAttribute(
                        "aria-label",
                        saved
                            ? "Manage saved service"
                            : "Save service"
                    );

                }
            );

    }


    function bindModalActions() {

        modal
            .querySelectorAll(
                "[data-toggle-collection]"
            )
            .forEach(
                function (button) {

                    button.addEventListener(
                        "click",
                        async function () {

                            const id =
                                button.dataset
                                    .toggleCollection;


                            button.disabled =
                                true;


                            try {

                                const data =
                                    await postAction(
                                        {
                                            action:
                                                "toggle_collection",

                                            collection_id:
                                                id,
                                        }
                                    );


                                button.classList.toggle(
                                    "selected",
                                    data.selected
                                );


                                const check =
                                    button.querySelector(
                                        ".bnx-save-collection-check"
                                    );


                                if (check) {

                                    check.textContent =
                                        data.selected
                                            ? "✓"
                                            : "+";

                                }


                                updateBookmarkButtons(
                                    currentServiceId,
                                    true
                                );

                            }

                            catch (error) {

                                alert(
                                    error.message
                                );

                            }

                            finally {

                                button.disabled =
                                    false;

                            }

                        }
                    );

                }
            );


        const createButton =
            modal.querySelector(
                "[data-create-inline-collection]"
            );


        const form =
            modal.querySelector(
                "[data-inline-collection-form]"
            );


        if (
            createButton
            &&
            form
        ) {

            createButton.addEventListener(
                "click",
                function () {

                    createButton.hidden =
                        true;

                    form.hidden =
                        false;


                    const input =
                        form.querySelector(
                            'input[name="name"]'
                        );


                    if (input) {

                        input.focus();

                    }

                }
            );


            const cancel =
                form.querySelector(
                    "[data-cancel-inline]"
                );


            if (cancel) {

                cancel.addEventListener(
                    "click",
                    function () {

                        form.hidden =
                            true;

                        createButton.hidden =
                            false;

                    }
                );

            }


            form.addEventListener(
                "submit",
                async function (event) {

                    event.preventDefault();


                    const formData =
                        new FormData(
                            form
                        );


                    try {

                        await postAction(
                            {
                                action:
                                    "create_and_add",

                                name:
                                    formData.get(
                                        "name"
                                    )
                                    || "",

                                note:
                                    formData.get(
                                        "note"
                                    )
                                    || "",
                            }
                        );


                        updateBookmarkButtons(
                            currentServiceId,
                            true
                        );


                        const state =
                            await loadCollections(
                                currentServiceId
                            );


                        renderState(
                            state
                        );

                    }

                    catch (error) {

                        alert(
                            error.message
                        );

                    }

                }
            );

        }


        const remove =
            modal.querySelector(
                "[data-remove-entire-save]"
            );


        if (remove) {

            remove.addEventListener(
                "click",
                async function () {

                    const confirmed =
                        window.confirm(
                            "Remove this service from all saved collections?"
                        );


                    if (!confirmed) {
                        return;
                    }


                    try {

                        await postAction(
                            {
                                action:
                                    "remove_saved",
                            }
                        );


                        updateBookmarkButtons(
                            currentServiceId,
                            false
                        );


                        closeModal();


                        if (
                            window.location.pathname
                            === "/toolkit/saved/"
                        ) {

                            window.location.reload();

                        }

                    }

                    catch (error) {

                        alert(
                            error.message
                        );

                    }

                }
            );

        }

    }


    async function openForService(
        serviceId
    ) {

        currentServiceId =
            String(
                serviceId
            );


        ensureModal();


        modal.hidden =
            false;


        document.body.classList.add(
            "bnx-modal-open"
        );


        const content =
            modal.querySelector(
                "[data-save-collection-content]"
            );


        content.innerHTML = `
            <div class="bnx-modal-loading">
                Loading collections…
            </div>
        `;


        try {

            const state =
                await loadCollections(
                    currentServiceId
                );


            renderState(
                state
            );

        }

        catch (error) {

            content.innerHTML = `
                <div class="bnx-modal-error">
                    ${
                        escapeHtml(
                            error.message
                        )
                    }
                </div>
            `;

        }

    }


    // -------------------------------------------------------
    // Capture existing bookmark forms BEFORE older save JS.
    // No existing search / matcher code has to be rewritten.
    // -------------------------------------------------------

    document.addEventListener(
        "submit",
        function (event) {

            const form =
                event.target;


            if (
                !form
                ||
                form.tagName !== "FORM"
            ) {

                return;

            }


            const action =
                form.getAttribute(
                    "action"
                )
                || "";


            const match =
                action.match(
                    SAVE_ACTION_PATTERN
                );


            if (!match) {
                return;
            }


            event.preventDefault();

            event.stopPropagation();

            event.stopImmediatePropagation();


            openForService(
                match[1]
            );

        },
        true
    );


    document.addEventListener(
        "click",
        function (event) {

            const manual =
                event.target.closest(
                    "[data-bnx-manage-saved]"
                );


            if (!manual) {
                return;
            }


            event.preventDefault();


            openForService(
                manual.dataset.serviceId
            );

        }
    );


    document.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Escape"
                &&
                modal
                &&
                !modal.hidden
            ) {

                closeModal();

            }

        }
    );

})();
