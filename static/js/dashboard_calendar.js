(function () {
    "use strict";

    const form = document.getElementById(
        "calendar-range-form"
    );

    if (!form) {
        return;
    }

    const startInput = document.getElementById(
        "calendar-start"
    );

    const endInput = document.getElementById(
        "calendar-end"
    );

    const rangeLabel = document.getElementById(
        "calendar-range-label"
    );

    const days = Array.from(
        document.querySelectorAll(
            ".calendar-day"
        )
    );

    let rangeStart = null;
    let rangeEnd = null;


    function formatDate(value) {
        const date = new Date(
            value + "T00:00:00"
        );

        return date.toLocaleDateString(
            "en-IN",
            {
                day: "2-digit",
                month: "short",
                year: "numeric"
            }
        );
    }


    function updateSelection() {
        days.forEach(function (day) {
            const value = day.dataset.date;

            day.classList.remove(
                "range-preview"
            );

            if (
                rangeStart
                && rangeEnd
                && value >= rangeStart
                && value <= rangeEnd
            ) {
                day.classList.add(
                    "range-preview"
                );
            }

            else if (
                rangeStart
                && !rangeEnd
                && value === rangeStart
            ) {
                day.classList.add(
                    "range-preview"
                );
            }
        });


        if (rangeStart && rangeEnd) {
            startInput.value = rangeStart;
            endInput.value = rangeEnd;

            rangeLabel.textContent =
                formatDate(rangeStart)
                + " — "
                + formatDate(rangeEnd);
        }

        else if (rangeStart) {
            startInput.value = rangeStart;
            endInput.value = rangeStart;

            rangeLabel.textContent =
                formatDate(rangeStart);
        }
    }


    days.forEach(function (day) {

        day.addEventListener(
            "click",
            function () {

                const value = day.dataset.date;

                if (
                    !rangeStart
                    || (
                        rangeStart
                        && rangeEnd
                    )
                ) {
                    rangeStart = value;
                    rangeEnd = null;
                }

                else {
                    if (value < rangeStart) {
                        rangeEnd = rangeStart;
                        rangeStart = value;
                    }
                    else {
                        rangeEnd = value;
                    }
                }

                updateSelection();
            }
        );

    });

})();
