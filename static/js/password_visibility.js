/* BNW_PASSWORD_VISIBILITY_V1 */
(function () {
    "use strict";

    document
        .querySelectorAll('input[type="password"]')
        .forEach(function (input, index) {
            if (
                input.closest(
                    ".bnx-password-control"
                )
            ) {
                return;
            }

            if (!input.id) {
                input.id = (
                    "bnx-password-input-"
                    + String(index + 1)
                );
            }

            const wrapper = (
                document.createElement("div")
            );

            wrapper.className = (
                "bnx-password-control"
            );

            input.parentNode.insertBefore(
                wrapper,
                input
            );

            wrapper.appendChild(input);

            const button = (
                document.createElement("button")
            );

            button.type = "button";
            button.className = (
                "bnx-password-toggle"
            );

            button.setAttribute(
                "aria-controls",
                input.id
            );

            button.setAttribute(
                "aria-label",
                "Show password"
            );

            button.setAttribute(
                "aria-pressed",
                "false"
            );

            button.innerHTML = `
                <svg class="bnx-eye-on"
                     viewBox="0 0 24 24"
                     aria-hidden="true">
                    <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path>
                    <circle cx="12" cy="12" r="2.75"></circle>
                </svg>

                <svg class="bnx-eye-off"
                     viewBox="0 0 24 24"
                     aria-hidden="true">
                    <path d="m3 3 18 18"></path>
                    <path d="M6.7 6.7C4.8 8.1 3.3 10 2.5 12c1.7 4.6 5.2 7 9.5 7 1.9 0 3.6-.5 5-1.4"></path>
                    <path d="M10.7 5.1A10 10 0 0 1 12 5c4.3 0 7.8 2.4 9.5 7a12 12 0 0 1-1.2 2.4"></path>
                    <path d="M14.1 14.1a3 3 0 0 1-4.2-4.2"></path>
                </svg>
            `;

            wrapper.appendChild(button);

            button.addEventListener(
                "click",
                function () {
                    const reveal = (
                        input.type === "password"
                    );

                    input.type = (
                        reveal
                            ? "text"
                            : "password"
                    );

                    button.setAttribute(
                        "aria-pressed",
                        String(reveal)
                    );

                    button.setAttribute(
                        "aria-label",
                        reveal
                            ? "Hide password"
                            : "Show password"
                    );

                    input.focus();
                }
            );
        });
})();
