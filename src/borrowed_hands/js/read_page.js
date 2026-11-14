// Collects the current page as a list of items for Claude (formatted in pagetext.py).
// Interactive elements get a number and a data-hands-id attribute so they can be highlighted
// later. Password values are never included.
//   {t: "text", s}            plain text (one block)
//   {t: "h", level, s}        heading
//   {t: "el", id, kind, label, extra, href}   interactive element
(function () {
	const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "IFRAME", "CANVAS"]);
	const INTERACTIVE = "a[href],button,input,select,textarea,summary,[role=button],[role=link]," +
		"[role=tab],[role=checkbox],[role=radio],[role=option],[role=menuitem],[contenteditable=true]";
	const items = [];
	let current = [];
	let count = 0;
	const flush = () => {
		const t = clean(current.join(" ").replace(/\s+([.,:;!?])/g, "$1"));
		if (t) items.push({ t: "text", s: t });
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
			// Never leak what the user typed into credential-ish fields (e-mail, username).
			const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
			const nameId = ((el.name || "") + " " + (el.id || "")).toLowerCase();
			const credential = type === "password" || type === "email"
				|| ac.includes("username") || ac.includes("email")
				|| /(^|[^a-z])(user|username|email|login)([^a-z]|$)/.test(nameId);
			if (type === "password") extra = " (password, value hidden)";
			else if (credential) extra = el.value ? " (filled, value hidden)" : "";
			else if (type === "checkbox" || type === "radio") extra = el.checked ? " [x]" : " [ ]";
			else if (type !== "hidden" && el.value) extra = ` value="${short(clean(el.value))}"`;
		} else if (tag === "select") {
			const opt = el.options[el.selectedIndex];
			extra = opt ? ` selected="${short(clean(opt.text))}"` : "";
		}
		const href = tag === "a" && el.href && !el.href.startsWith("javascript:") ? el.href : "";
		return { kind: kind, label: short(label), extra: extra, href: href };
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
			items.push(Object.assign({ t: "el", id: count }, describe(el)));
			return;
		}
		const h = /^H([1-6])$/.exec(el.tagName);
		if (h) {
			flush();
			const t = clean(el.innerText);
			if (t) items.push({ t: "h", level: Number(h[1]), s: t });
			return;
		}
		const block = !INLINE.has(getComputedStyle(el).display) || el.tagName === "BR";
		if (block) flush();
		for (const child of el.childNodes) walk(child);
		if (block) flush();
	}

	if (document.body) walk(document.body);
	flush();
	return { url: location.href, title: document.title, elements: count, items: items };
})();
