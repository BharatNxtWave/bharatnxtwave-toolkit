(function () {
    "use strict";


    function getDrilldownDate(url) {

        const params = url.searchParams;


        const start =
            params.get("start")
            ||
            params.get("start_date");


        const end =
            params.get("end")
            ||
            params.get("end_date");


        /*
         * Existing chart drilldown uses the same
         * start/end date when a daily bar is clicked.
         */

        if (
            start
            &&
            end
            &&
            start === end
        ) {
            return start;
        }


        return null;
    }



    function convertExistingLinks() {

        document
            .querySelectorAll("a[href]")
            .forEach(function (link) {

                try {

                    const url = new URL(
                        link.href,
                        window.location.origin
                    );


                    const date =
                        getDrilldownDate(url);


                    if (!date) {
                        return;
                    }


                    /*
                     * Only rewrite dashboard date
                     * drilldown links.
                     *
                     * Do not interfere with unrelated
                     * links elsewhere in the application.
                     */

                    const looksLikeDashboardDateLink =
                        url.searchParams.has("preset")
                        ||
                        url.searchParams.has("start")
                        ||
                        url.searchParams.has(
                            "start_date"
                        );


                    if (
                        !looksLikeDashboardDateLink
                    ) {
                        return;
                    }


                    link.href =
                        "/search-activity/?date="
                        +
                        encodeURIComponent(date);


                    link.dataset.searchDrilldown =
                        "true";


                    link.title =
                        "View search activity for "
                        +
                        date;

                }

                catch (error) {

                    /*
                     * Ignore malformed/non-http links.
                     */

                }

            });

    }



    /*
     * Run after dashboard HTML is ready.
     */

    if (
        document.readyState === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            convertExistingLinks
        );

    }

    else {

        convertExistingLinks();

    }



    /*
     * Also catch links that may be rendered
     * dynamically.
     */

    document.addEventListener(
        "click",
        function (event) {

            const link =
                event.target.closest(
                    "a[href]"
                );


            if (!link) {
                return;
            }


            try {

                const url = new URL(
                    link.href,
                    window.location.origin
                );


                const date =
                    getDrilldownDate(url);


                if (
                    date
                    &&
                    !url.pathname.includes(
                        "/search-activity/"
                    )
                ) {

                    event.preventDefault();


                    window.location.href =
                        "/search-activity/?date="
                        +
                        encodeURIComponent(date);

                }

            }

            catch (error) {

                /*
                 * Leave normal navigation untouched.
                 */

            }

        },
        true
    );

})();
