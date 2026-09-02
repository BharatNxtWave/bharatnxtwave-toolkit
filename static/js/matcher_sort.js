(function () {
    "use strict";

    const sortSelect = document.getElementById(
        "matcher-result-sort"
    );

    if (!sortSelect) {
        return;
    }


    const grids = Array.from(
        document.querySelectorAll(
            ".matcher-results-grid"
        )
    );


    grids.forEach(function (grid) {

        const cards = Array.from(
            grid.querySelectorAll(
                ".matcher-result-card"
            )
        );

        cards.forEach(function (card, index) {
            card.dataset.originalOrder = index;
        });

    });


    function sortCards(mode) {

        grids.forEach(function (grid) {

            const cards = Array.from(
                grid.querySelectorAll(
                    ".matcher-result-card"
                )
            );


            cards.sort(function (a, b) {

                if (mode === "type") {

                    return (
                        a.dataset.kind || ""
                    ).localeCompare(
                        b.dataset.kind || ""
                    );

                }


                if (mode === "verified") {

                    return (
                        Number(
                            b.dataset.verified || 0
                        )
                        -
                        Number(
                            a.dataset.verified || 0
                        )
                    );

                }


                return (
                    Number(
                        a.dataset.originalOrder
                    )
                    -
                    Number(
                        b.dataset.originalOrder
                    )
                );

            });


            cards.forEach(function (card) {
                grid.appendChild(card);
            });

        });

    }


    sortSelect.addEventListener(
        "change",
        function () {
            sortCards(
                sortSelect.value
            );
        }
    );

})();
