(function () {
    "use strict";

    const MAX_BYTES = 20 * 1024 * 1024;
    const ALLOWED = new Map([
        ["application/pdf", "PDF"],
        ["image/png", "PNG image"],
        ["image/jpeg", "JPEG image"],
    ]);

    const EXTENSION_TYPES = new Map([
        ["pdf", "application/pdf"],
        ["png", "image/png"],
        ["jpg", "image/jpeg"],
        ["jpeg", "image/jpeg"],
    ]);

    function formatBytes(value) {
        const bytes = Number(value || 0);

        if (bytes < 1024 * 1024) {
            return (bytes / 1024).toFixed(1) + " KB";
        }

        return (bytes / (1024 * 1024)).toFixed(2) + " MB";
    }

    function initBdeViewer() {
        const dialog = document.querySelector("[data-flyer-dialog]");
        const openButton = document.querySelector("[data-flyer-open]");
        const closeButton = dialog
            ? dialog.querySelector("[data-flyer-close]")
            : null;

        if (!dialog || !openButton || !closeButton) {
            return;
        }

        function closeDialog() {
            dialog.close();
            document.body.classList.remove("bnx-flyer-dialog-open");
            openButton.focus();
        }

        openButton.addEventListener("click", function () {
            dialog.showModal();
            document.body.classList.add("bnx-flyer-dialog-open");
            closeButton.focus();
        });

        closeButton.addEventListener("click", closeDialog);

        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                closeDialog();
            }
        });

        dialog.addEventListener("close", function () {
            document.body.classList.remove("bnx-flyer-dialog-open");
        });
    }

    function initUploadPreview() {
        const page = document.querySelector("[data-flyer-upload-page]");

        if (!page) {
            return;
        }

        const form = page.querySelector("[data-flyer-upload-form]");
        const input = page.querySelector("[data-flyer-file]");
        const preview = page.querySelector("[data-new-flyer-preview]");
        const state = page.querySelector("[data-new-flyer-state]");
        const metadata = page.querySelector("[data-new-flyer-meta]");
        const removeButton = page.querySelector("[data-remove-flyer]");
        const submitButton = page.querySelector("[data-flyer-submit]");
        const errorBox = page.querySelector("[data-flyer-browser-error]");
        let objectUrl = "";

        if (
            !form ||
            !input ||
            !preview ||
            !state ||
            !metadata ||
            !removeButton ||
            !submitButton ||
            !errorBox
        ) {
            return;
        }

        function releaseObjectUrl() {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = "";
            }
        }

        function showEmpty() {
            releaseObjectUrl();
            preview.innerHTML = `
                <div class="bnx-flyer-preview-empty">
                    <strong>Live preview appears here</strong>
                    <span>Select a file below. Nothing is saved yet.</span>
                </div>
            `;
            state.textContent = "Nothing selected";
            metadata.hidden = true;
            metadata.innerHTML = "";
            removeButton.hidden = true;
            submitButton.disabled = true;
        }

        function showError(message) {
            errorBox.textContent = message;
            errorBox.hidden = false;
            showEmpty();
        }

        function clearError() {
            errorBox.textContent = "";
            errorBox.hidden = true;
        }

        input.addEventListener("change", function () {
            clearError();
            releaseObjectUrl();

            const file = input.files && input.files[0];

            if (!file) {
                showEmpty();
                return;
            }

            const extension = file.name.includes(".")
                ? file.name.split(".").pop().toLowerCase()
                : "";
            const expectedType = EXTENSION_TYPES.get(extension) || "";
            const previewType = ALLOWED.has(file.type)
                ? file.type
                : expectedType;

            if (!previewType) {
                input.value = "";
                showError("Choose a PDF, JPG, JPEG or PNG flyer.");
                return;
            }

            if (
                expectedType &&
                ALLOWED.has(file.type) &&
                file.type !== expectedType
            ) {
                input.value = "";
                showError("The file type does not match its filename extension.");
                return;
            }

            if (!file.size || file.size > MAX_BYTES) {
                input.value = "";
                showError("The flyer must be larger than 0 bytes and no more than 20 MB.");
                return;
            }

            objectUrl = URL.createObjectURL(file);

            if (previewType === "application/pdf") {
                preview.innerHTML = "";
                const frame = document.createElement("iframe");
                frame.src = objectUrl + "#page=1&zoom=page-width";
                frame.title = "Newly selected flyer preview";
                preview.appendChild(frame);
            }
            else {
                preview.innerHTML = "";
                const image = document.createElement("img");
                image.src = objectUrl;
                image.alt = "Newly selected flyer preview";
                preview.appendChild(image);
            }

            state.textContent = "Ready to review";
            metadata.hidden = false;
            metadata.innerHTML = "";

            const filename = document.createElement("strong");
            filename.textContent = file.name;

            const details = document.createElement("span");
            details.textContent = ALLOWED.get(previewType) + " · " + formatBytes(file.size);

            metadata.append(filename, details);
            removeButton.hidden = false;
            submitButton.disabled = false;
        });

        removeButton.addEventListener("click", function () {
            input.value = "";
            clearError();
            showEmpty();
            input.focus();
        });

        form.addEventListener("submit", function () {
            submitButton.disabled = true;
            submitButton.textContent = "Validating and saving…";
            form.setAttribute("aria-busy", "true");
        });

        window.addEventListener("beforeunload", releaseObjectUrl);

        Array.from(
            page.querySelectorAll("[data-flyer-restore-form]")
        ).forEach(function (restoreForm) {
            restoreForm.addEventListener("submit", function (event) {
                if (!window.confirm(
                    "Restore this historical flyer as a new current version?"
                )) {
                    event.preventDefault();
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initBdeViewer();
        initUploadPreview();
    });
}());
