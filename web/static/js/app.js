/* Amoja Social Manager — shell behaviour. */

(function () {
    "use strict";

    const THEME_KEY = "amoja-theme";
    const root = document.documentElement;

    function initTheme() {
        const saved = window.localStorage.getItem(THEME_KEY);
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        if (saved === "dark" || (!saved && prefersDark)) {
            root.classList.add("dark");
        }
    }

    function toggleTheme() {
        const isDark = root.classList.toggle("dark");
        window.localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
    }

    function refreshIcons() {
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    function updateTitle() {
        const main = document.getElementById("page-content");
        const title = main && main.dataset.pageTitle;
        if (title) {
            document.title = title + " \u00b7 Amoja Social";
        }
    }

    function updateActiveNav() {
        const path = window.location.pathname;
        document.querySelectorAll(".sidebar-link").forEach(function (link) {
            const href = link.getAttribute("href");
            const isActive = href === path || (href === "/" && path === "/");
            link.classList.toggle("active", isActive);
            if (isActive) {
                link.setAttribute("aria-current", "page");
            } else {
                link.removeAttribute("aria-current");
            }
        });
    }

    function onReady() {
        refreshIcons();
        updateTitle();
        updateActiveNav();
    }

    initTheme();

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", onReady);
    } else {
        onReady();
    }

    document.addEventListener("click", function (event) {
        if (event.target.closest("[data-theme-toggle]")) {
            toggleTheme();
        }
    });

    document.addEventListener("htmx:afterSwap", function () {
        refreshIcons();
        updateTitle();
        updateActiveNav();
    });

    if (document.body) {
        document.body.addEventListener("htmx:configRequest", function (event) {
            event.detail.withCredentials = true;
        });
    }
})();
