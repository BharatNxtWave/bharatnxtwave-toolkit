(function () {
    "use strict";


    function initializeActivityChart() {

        document
            .querySelectorAll(
                ".search-bar-fill[data-height]"
            )
            .forEach(function (bar) {

                let height = Number(
                    bar.dataset.height
                );

                if (!Number.isFinite(height)) {
                    height = 0;
                }

                height = Math.max(
                    0,
                    Math.min(100, height)
                );

                if (
                    height > 0
                    &&
                    height < 5
                ) {
                    height = 5;
                }

                bar.style.height =
                    height + "%";
            });



        document
            .querySelectorAll(
                ".search-bar-column[data-total]"
            )
            .forEach(function (column) {

                const total = Number(
                    column.dataset.total
                );


                if (
                    !Number.isFinite(total)
                    ||
                    total <= 0
                ) {

                    column.classList.add(
                        "zero-activity"
                    );


                    const link =
                        column.closest("a[href]");


                    if (link) {

                        link.removeAttribute(
                            "href"
                        );

                        link.setAttribute(
                            "aria-disabled",
                            "true"
                        );

                        link.title =
                            "No Toolkit activity recorded";
                    }

                }

                else {

                    column.classList.remove(
                        "zero-activity"
                    );

                    column.title =
                        total
                        +
                        (
                            total === 1
                            ? " recorded action"
                            : " recorded actions"
                        );
                }

            });
    }


    if (
        document.readyState
        === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            initializeActivityChart
        );

    }

    else {

        initializeActivityChart();

    }

})();
