/* BNW_ACTIVITY_DASHBOARD_V2 */
(() => {
    "use strict";

    const root = document.querySelector("[data-bnw-activity-v2]");
    if (!root) return;

    const segments = Array.from(
        root.querySelectorAll("[data-bnw-segment]")
    );
    const seriesButtons = Array.from(
        root.querySelectorAll("[data-bnw-series]")
    );
    const centreLabel = root.querySelector("[data-bnw-centre-label]");
    const centreValue = root.querySelector("[data-bnw-centre-value]");
    const centreDetail = root.querySelector("[data-bnw-centre-detail]");
    const resetButton = root.querySelector("[data-bnw-reset]");
    const total = seriesButtons.reduce(
        (sum, button) => sum + (Number(button.dataset.count) || 0),
        0,
    );
    let lockedKey = null;

    const matchingButton = (key) => (
        seriesButtons.find((button) => button.dataset.bnwSeries === key)
    );
    const matchingSegment = (key) => (
        segments.find((segment) => segment.dataset.bnwSegment === key)
    );

    const showTotal = () => {
        if (!centreLabel || !centreValue || !centreDetail) return;
        centreLabel.textContent = total ? "TOTAL ACTIONS" : "NO ACTIVITY";
        centreValue.textContent = String(total);
        centreDetail.textContent = "Selected period";
    };

    const showSeries = (key) => {
        const button = matchingButton(key);
        if (!button || !centreLabel || !centreValue || !centreDetail) return;
        centreLabel.textContent = button.dataset.label || "ACTIVITY";
        centreValue.textContent = button.dataset.count || "0";
        centreDetail.textContent = `${button.dataset.percentage || 0}% of all actions`;
    };

    const paint = (key = null) => {
        segments.forEach((segment) => {
            const active = segment.dataset.bnwSegment === key;
            segment.classList.toggle("is-active", active);
            segment.classList.toggle("is-muted", Boolean(key) && !active);
        });
        seriesButtons.forEach((button) => {
            const active = button.dataset.bnwSeries === key;
            button.classList.toggle("is-active", active);
            button.classList.toggle("is-muted", Boolean(key) && !active);
        });
        key ? showSeries(key) : showTotal();
        if (resetButton) resetButton.hidden = !lockedKey;
    };

    const bindSeriesControl = (control, key) => {
        control.addEventListener("mouseenter", () => {
            if (!lockedKey) paint(key);
        });
        control.addEventListener("mouseleave", () => {
            if (!lockedKey) paint();
        });
        control.addEventListener("focus", () => {
            if (!lockedKey) paint(key);
        });
        control.addEventListener("blur", () => {
            if (!lockedKey) paint();
        });
        control.addEventListener("click", () => {
            lockedKey = lockedKey === key ? null : key;
            paint(lockedKey);
        });
        control.addEventListener("keydown", (event) => {
            if (
                control.namespaceURI === "http://www.w3.org/2000/svg"
                && (event.key === "Enter" || event.key === " ")
            ) {
                event.preventDefault();
                control.dispatchEvent(new MouseEvent("click", { bubbles: true }));
            }
        });
    };

    seriesButtons.forEach((button) => {
        bindSeriesControl(button, button.dataset.bnwSeries);
    });
    segments.forEach((segment) => {
        bindSeriesControl(segment, segment.dataset.bnwSegment);
    });

    resetButton?.addEventListener("click", () => {
        lockedKey = null;
        paint();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && lockedKey) {
            lockedKey = null;
            paint();
        }
    });

    segments.forEach((segment) => {
        const finalDash = segment.getAttribute("stroke-dasharray");
        segment.setAttribute("stroke-dasharray", "0 100");
        requestAnimationFrame(() => requestAnimationFrame(() => {
            segment.setAttribute("stroke-dasharray", finalDash);
        }));
    });

    root.querySelectorAll("[data-bnw-exact-bar]").forEach((bar) => {
        const finalWidth = Number(bar.dataset.width) || 0;
        bar.style.width = "0%";
        requestAnimationFrame(() => requestAnimationFrame(() => {
            bar.style.width = `${finalWidth}%`;
        }));
    });

    const days = Array.from(root.querySelectorAll("[data-bnw-day]"));
    days.forEach((day) => {
        const bar = day.querySelector("[data-bnw-day-bar]");
        if (!bar) return;
        const finalHeight = Number(bar.dataset.height) || 0;
        bar.style.height = "0%";
        requestAnimationFrame(() => requestAnimationFrame(() => {
            bar.style.height = `${finalHeight}%`;
        }));
    });

    const tooltip = document.createElement("div");
    tooltip.className = "bnw-v2-tooltip";
    tooltip.setAttribute("role", "tooltip");
    document.body.appendChild(tooltip);
    let activeDay = null;

    const positionTooltip = (day) => {
        const rect = day.getBoundingClientRect();
        const width = 250;
        const margin = 12;
        const left = Math.min(
            window.innerWidth - width - margin,
            Math.max(margin, rect.left + rect.width / 2 - width / 2),
        );
        const height = tooltip.offsetHeight || 140;
        const above = rect.top - height - 10;
        const top = above > margin
            ? above
            : Math.min(window.innerHeight - height - margin, rect.bottom + 10);
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    };

    const showTooltip = (day) => {
        activeDay = day;
        tooltip.replaceChildren();

        const date = document.createElement("strong");
        date.textContent = day.querySelector("time")?.textContent?.trim() || "Selected day";
        const totalText = document.createElement("span");
        const dayTotal = Number(day.dataset.total) || 0;
        totalText.textContent = `${dayTotal} total action${dayTotal === 1 ? "" : "s"}`;
        tooltip.append(date, totalText);

        const sourceRows = Array.from(
            day.querySelectorAll("[data-bnw-day-segment]")
        );
        if (sourceRows.length) {
            const list = document.createElement("div");
            list.className = "bnw-v2-tooltip-list";
            sourceRows.forEach((source) => {
                const row = document.createElement("div");
                row.className = "bnw-v2-tooltip-row";
                const dot = document.createElement("i");
                dot.style.background = source.dataset.color || "#64748b";
                const label = document.createElement("span");
                label.textContent = source.dataset.label || "Activity";
                const count = document.createElement("b");
                count.textContent = source.dataset.count || "0";
                row.append(dot, label, count);
                list.appendChild(row);
            });
            tooltip.appendChild(list);
        }

        tooltip.classList.add("is-visible");
        positionTooltip(day);
    };

    const hideTooltip = () => {
        activeDay = null;
        tooltip.classList.remove("is-visible");
    };

    days.forEach((day) => {
        day.addEventListener("mouseenter", () => showTooltip(day));
        day.addEventListener("mouseleave", hideTooltip);
        day.addEventListener("focus", () => showTooltip(day));
        day.addEventListener("blur", hideTooltip);
    });
    window.addEventListener("resize", () => {
        if (activeDay) positionTooltip(activeDay);
    }, { passive: true });
    window.addEventListener("scroll", () => {
        if (activeDay) positionTooltip(activeDay);
    }, { passive: true });

    showTotal();
})();
