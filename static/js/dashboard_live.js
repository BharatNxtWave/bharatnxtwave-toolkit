(function () {
    "use strict";

    const REFRESH_MS = 60000;
    const IDLE_REQUIRED_MS = 20000;

    let lastInteraction = Date.now();

    [
        "click",
        "keydown",
        "change",
        "mousemove",
        "touchstart"
    ].forEach(function (eventName) {

        document.addEventListener(
            eventName,
            function () {
                lastInteraction = Date.now();
            },
            { passive: true }
        );

    });


    setInterval(function () {

        if (document.visibilityState !== "visible") {
            return;
        }

        const idleFor = (
            Date.now() - lastInteraction
        );

        if (idleFor < IDLE_REQUIRED_MS) {
            return;
        }

        window.location.reload();

    }, REFRESH_MS);

})();
