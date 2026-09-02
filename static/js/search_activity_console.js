(function () {
    "use strict";


    document
        .querySelectorAll(
            ".search-time-event[data-left]"
        )
        .forEach(function (event) {

            let position = Number(
                event.dataset.left
            );


            if (
                !Number.isFinite(position)
            ) {
                position = 0;
            }


            position = Math.max(
                0,
                Math.min(
                    100,
                    position
                )
            );


            event.style.left =
                position + "%";

        });

})();
