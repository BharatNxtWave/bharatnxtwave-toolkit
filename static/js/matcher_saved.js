(function () {
    "use strict";

    const forms = document.querySelectorAll(
        ".matcher-save-form"
    );

    forms.forEach(function (form) {

        form.addEventListener(
            "submit",
            async function (event) {

                event.preventDefault();

                const button = form.querySelector(
                    ".matcher-save-button"
                );

                const csrf = form.querySelector(
                    'input[name="csrfmiddlewaretoken"]'
                );

                if (!button || !csrf) {
                    return;
                }

                button.disabled = true;

                try {

                    const response = await fetch(
                        form.action,
                        {
                            method: "POST",

                            headers: {
                                "X-Requested-With":
                                    "XMLHttpRequest",

                                "X-CSRFToken":
                                    csrf.value,
                            },

                            body: new FormData(
                                form
                            ),
                        }
                    );


                    if (!response.ok) {
                        throw new Error(
                            "Save request failed"
                        );
                    }


                    const data = await response.json();


                    if (data.saved) {

                        button.classList.add(
                            "saved"
                        );

                        button.innerHTML =
                            '<span class="bn-bookmark-icon is-saved" aria-hidden="true"></span><span>Saved</span>';

                    }

                    else {

                        button.classList.remove(
                            "saved"
                        );

                        button.innerHTML =
                            '<span class="bn-bookmark-icon" aria-hidden="true"></span><span>Save</span>';

                    }

                }

                catch (error) {

                    button.textContent =
                        "Try Again";

                }

                finally {

                    button.disabled = false;

                }

            }
        );

    });

})();
