(function () {
    "use strict";

    if (!navigator.geolocation) {
        return;
    }

    const storageKey = "bharatnxt_location_sent";

    if (sessionStorage.getItem(storageKey) === "1") {
        return;
    }

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split(";") : [];

        for (const cookie of cookies) {
            const trimmed = cookie.trim();

            if (trimmed.startsWith(name + "=")) {
                return decodeURIComponent(
                    trimmed.substring(name.length + 1)
                );
            }
        }

        return null;
    }

    function getCsrfToken() {
        const formToken = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (
            formToken
            && typeof formToken.value === "string"
            && formToken.value.trim()
        ) {
            return formToken.value.trim();
        }

        return getCookie("csrftoken");
    }

    navigator.geolocation.getCurrentPosition(
        function (position) {

            const csrfToken = getCsrfToken();

            if (!csrfToken) {
                return;
            }

            fetch("/session/location/", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                })
            })
            .then(function (response) {
                if (response.ok) {
                    sessionStorage.setItem(storageKey, "1");
                }
            })
            .catch(function () {
                // Location is optional. Do not interrupt the employee.
            });
        },

        function () {
            // Permission denied or location unavailable.
            // The application continues normally.
        },

        {
            enableHighAccuracy: false,
            timeout: 8000,
            maximumAge: 300000
        }
    );
})();


document.addEventListener("submit", function (event) {
    if (
        event.target &&
        event.target.classList.contains("topbar-logout-form")
    ) {
        sessionStorage.removeItem("bharatnxt_location_sent");
    }
});
