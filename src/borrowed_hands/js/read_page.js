// Turns the current page into plain text for Claude. Interactive elements get a number
// ([12] button "Hledat") and a data-hands-id attribute so they can be highlighted later.
// Password values are never included.
(function () {
	const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "IFRAME", "CANVAS"]);
	const INTERACTIVE = "a[href],button,input,select,textarea,summary,[role=button],[role=link]," +
		"[role=tab],[role=checkbox],[role=radio],[role=option],[role=menuitem],[contenteditable=true]";
	const lines = [];
	let current = [];
	let count = 0;
	const flush = () => {
		const t = clean(current.join(" ").replace(/\s+([.,:;!?])/g, "$1"));
		if (t) lines.push(t);
		current = [];
	};
	const INLINE = new Set(["inline", "inline-block", "inline-flex", "contents"]);

	document.querySelectorAll("[data-hands-id]").forEach(el => el.removeAttribute("data-hands-id"));

	const clean = s => (s || "").replace(/\s+/g, " ").trim();
	const short = s => (s.length > 140 ? s.slice(0, 140) + "…" : s);

	function visible(el) {
		if (el.checkVisibility) return el.checkVisibility({ visibilityProperty: true });
		const s = getComputedStyle(el);
		return s.display !== "none" && s.visibility !== "hidden";
	}

	function describe(el) {
		const tag = el.tagName.toLowerCase();
		const role = el.getAttribute("role");
		let kind = role || tag;
		if (tag === "a") kind = "link";
		let label = clean(el.getAttribute("aria-label") || el.innerText || el.title || el.alt || "");
		let extra = "";
		if (tag === "input" || tag === "textarea") {
			const type = (el.getAttribute("type") || "text").toLowerCase();
			kind = tag === "textarea" ? "textarea" : "input:" + type;
			label = label || clean(el.placeholder || el.name || "");
			if (type === "password") extra = " (password, value hidden)";
			else if (type === "checkbox" || type === "radio") extra = el.checked ? " [x]" : " [ ]";
			else if (type !== "hidden" && el.value) extra = ` value="${short(clean(el.value))}"`;
		} else if (tag === "select") {
			const opt = el.options[el.selectedIndex];
			extra = opt ? ` selected="${short(clean(opt.text))}"` : "";
		}
		if (tag === "a" && el.href && !el.href.startsWith("javascript:")) extra += ` -> ${el.href}`;
		return `${kind} "${short(label)}"${extra}`;
	}

	function walk(node) {
		if (node.nodeType === Node.TEXT_NODE) {
			const t = clean(node.textContent);
			if (t) current.push(t);
			return;
		}
		if (node.nodeType !== Node.ELEMENT_NODE) return;
		const el = node;
		if (SKIP.has(el.tagName.toUpperCase())) return;
		if (el.getAttribute("type") === "hidden") return;
		if (!visible(el)) return;
		if (el.matches(INTERACTIVE)) {
			flush();
			count += 1;
			el.setAttribute("data-hands-id", String(count));
			lines.push(`[${count}] ${describe(el)}`);
			return;
		}
		const h = /^H([1-6])$/.exec(el.tagName);
		if (h) {
			flush();
			const t = clean(el.innerText);
			if (t) lines.push("#".repeat(Number(h[1])) + " " + t);
			return;
		}
		const block = !INLINE.has(getComputedStyle(el).display) || el.tagName === "BR";
		if (block) flush();
		for (const child of el.childNodes) walk(child);
		if (block) flush();
	}

	if (document.body) walk(document.body);
	flush();
	// Merge consecutive duplicates (common with nested markup).
	const text = lines.filter((l, i) => l !== lines[i - 1]).join("\n");
	return { url: location.href, title: document.title, elements: count, text: text };
})();
