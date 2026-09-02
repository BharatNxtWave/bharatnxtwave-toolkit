/* BNW_DASHBOARD_DATE_PICKER_V1 */

(function () {
    "use strict";

    const picker =
        document.querySelector(".bn-date-picker");

    if (!picker) {
        return;
    }

    document.addEventListener(
        "click",
        function (event) {
            if (
                picker.open
                && !picker.contains(event.target)
            ) {
                picker.removeAttribute("open");
            }
        }
    );
})();
