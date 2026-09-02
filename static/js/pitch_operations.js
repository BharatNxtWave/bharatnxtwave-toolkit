(function () {
    "use strict";


    /* =====================================================
       TIMELINE POSITIONING
    ===================================================== */

    document
        .querySelectorAll(
            ".pitch-axis-marker[data-left]"
        )
        .forEach(function (marker) {

            marker.style.left =
                marker.dataset.left + "%";

        });


    document
        .querySelectorAll(
            ".pitch-timeline-bar[data-left]"
        )
        .forEach(function (bar) {

            bar.style.left =
                bar.dataset.left + "%";

            bar.style.width =
                bar.dataset.width + "%";

        });



    /* =====================================================
       DRAWER
    ===================================================== */

    const drawer =
        document.getElementById(
            "pitch-ops-drawer"
        );

    const overlay =
        document.getElementById(
            "pitch-ops-overlay"
        );

    const closeButton =
        document.getElementById(
            "pitch-drawer-close"
        );


    if (
        !drawer
        ||
        !overlay
    ) {
        return;
    }


    function setText(id, value) {

        const element =
            document.getElementById(id);

        if (element) {

            element.textContent =
                value || "—";

        }

    }


    function openDrawer(button) {

        setText(
            "drawer-title",
            button.dataset.title
        );

        setText(
            "drawer-service-id",
            button.dataset.serviceId
        );

        setText(
            "drawer-sector",
            button.dataset.sector
        );

        setText(
            "drawer-status",
            button.dataset.status
        );

        setText(
            "drawer-effective",
            button.dataset.effective
        );

        setText(
            "drawer-pitch",
            button.dataset.pitch
        );

        setText(
            "drawer-deadline",
            button.dataset.deadline
        );

        setText(
            "drawer-days",
            button.dataset.days
        );

        setText(
            "drawer-updated",
            button.dataset.updated
        );

        setText(
            "drawer-verified",
            button.dataset.verified
        );


        const edit =
            document.getElementById(
                "drawer-edit"
            );

        const detail =
            document.getElementById(
                "drawer-detail"
            );


        if (edit) {

            edit.href =
                button.dataset.editUrl || "#";

        }


        if (detail) {

            detail.href =
                button.dataset.detailUrl || "#";

        }


        drawer.classList.add(
            "open"
        );

        overlay.classList.add(
            "open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "false"
        );

    }


    function closeDrawer() {

        drawer.classList.remove(
            "open"
        );

        overlay.classList.remove(
            "open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "true"
        );

    }


    document
        .querySelectorAll(
            ".ops-row-open"
        )
        .forEach(function (button) {

            button.addEventListener(
                "click",
                function () {

                    openDrawer(
                        button
                    );

                }
            );

        });


    if (closeButton) {

        closeButton.addEventListener(
            "click",
            closeDrawer
        );

    }


    overlay.addEventListener(
        "click",
        closeDrawer
    );


    document.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Escape"
            ) {

                closeDrawer();

            }

        }
    );

})();
