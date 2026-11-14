// Highlights element number %ID% from the last read_page and scrolls it into view.
(function (id) {
	document.querySelectorAll(".hands-highlight").forEach(el => {
		el.classList.remove("hands-highlight");
		el.style.outline = el.dataset.handsOldOutline || "";
	});
	if (!id) return true;
	const el = document.querySelector(`[data-hands-id="${id}"]`);
	if (!el) return false;
	el.dataset.handsOldOutline = el.style.outline;
	el.classList.add("hands-highlight");
	el.style.outline = "3px solid #fbbf24";
	el.style.outlineOffset = "2px";
	el.scrollIntoView({ block: "center", behavior: "smooth" });
	return true;
})(%ID%);
