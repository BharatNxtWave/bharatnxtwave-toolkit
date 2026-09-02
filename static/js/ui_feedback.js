(function () {
    "use strict";


    /* =====================================================
       FEEDBACK NOTIFICATIONS
    ===================================================== */

    document
        .querySelectorAll(
            ".bn-feedback-toast"
        )
        .forEach(function (toast) {


            function dismiss() {

                if (
                    toast.classList.contains(
                        "leaving"
                    )
                ) {
                    return;
                }


                toast.classList.add(
                    "leaving"
                );


                window.setTimeout(
                    function () {

                        toast.remove();

                    },
                    180
                );

            }


            const close =
                toast.querySelector(
                    ".bn-feedback-close"
                );


            if (close) {

                close.addEventListener(
                    "click",
                    dismiss
                );

            }


            const type =
                toast.dataset.feedbackType
                || "";


            const duration =
                (
                    type.includes("error")
                    ||
                    type.includes("warning")
                )
                ? 8000
                : 4300;


            window.setTimeout(
                dismiss,
                duration
            );

        });



    /* =====================================================
       POST ACTION PROGRESS
       Never reports success before server response.
    ===================================================== */

    document.addEventListener(
        "submit",
        function (event) {

            const form =
                event.target;


            if (
                !(form instanceof HTMLFormElement)
            ) {
                return;
            }


            const method =
                (
                    form.getAttribute(
                        "method"
                    )
                    || "get"
                ).toLowerCase();


            if (method !== "post") {
                return;
            }


            if (
                form.dataset.noLoading
                === "true"
            ) {
                return;
            }


            const submitButton =
                form.querySelector(
                    'button[type="submit"]'
                );


            if (!submitButton) {
                return;
            }


            window.setTimeout(
                function () {

                    if (
                        submitButton.disabled
                    ) {
                        return;
                    }


                    submitButton.disabled =
                        true;


                    submitButton.classList.add(
                        "bn-button-loading"
                    );


                    if (
                        submitButton.classList.contains(
                            "topbar-logout-button"
                        )
                    ) {

                        submitButton.textContent =
                            "Signing out…";

                        return;
                    }


                    submitButton.dataset.originalHtml =
                        submitButton.innerHTML;


                    submitButton.innerHTML =
                        '<span class="bn-loading-spinner" aria-hidden="true"></span>'
                        +
                        '<span>Working…</span>';

                },
                0
            );

        }
    );

})();
