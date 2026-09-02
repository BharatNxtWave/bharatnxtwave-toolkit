(function () {
    "use strict";


    /* =====================================================
       CHART HEIGHTS
    ===================================================== */

    document
        .querySelectorAll(
            ".bn-chart-bar[data-height]"
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
                Math.min(
                    100,
                    height
                )
            );


            if (
                height > 0
                &&
                height < 7
            ) {
                height = 7;
            }


            bar.style.height =
                height + "%";

        });



    /* =====================================================
       CLOSE DATE PICKER WHEN CLICKING OUTSIDE
    ===================================================== */

    const picker =
        document.querySelector(
            ".bn-date-picker"
        );


    if (picker) {

        document.addEventListener(
            "click",
            function (event) {

                if (
                    picker.open
                    &&
                    !picker.contains(
                        event.target
                    )
                ) {

                    picker.removeAttribute(
                        "open"
                    );

                }

            }
        );

    }

})();
