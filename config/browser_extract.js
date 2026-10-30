// Run by the careers-browser agent via browser_evaluate on a careers listing page.
// Replace __LINK_PATTERN__ and __COMPANY__ before use. Returns posting objects in the Posting schema.
// Descriptions are fetched from each posting page inside the browser (same site, same session).
async () => {
  const LINK_PATTERN = "__LINK_PATTERN__";
  const COMPANY = "__COMPANY__";
  const RELEVANT = /machine learning|\bML\b|\bAI\b|data scien|NLP|LLM|deep learning|computer vision|graduate|junior|entry/i;
  const seen = new Set();
  const links = [...document.querySelectorAll(`a[href*="${LINK_PATTERN}"]`)]
    .map(a => ({ text: a.innerText.replace(/\s+/g, " ").trim(), href: a.href.split("?")[0] }))
    .filter(l => l.text && RELEVANT.test(l.text) && !seen.has(l.href) && seen.add(l.href))
    .slice(0, 15);
  const out = [];
  for (const l of links) {
    try {
      const html = await (await fetch(l.href)).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      doc.querySelectorAll("script,style,nav,footer,header,svg").forEach(e => e.remove());
      const text = ((doc.querySelector("main") || doc.body).textContent || "").replace(/\s*\n\s*/g, "\n").replace(/[ \t]+/g, " ").trim();
      const title = l.text.split(/ Office:| Remote:| \| /)[0].trim();
      const location = (l.text.match(/(Office|Remote):.*/) || [""])[0];
      out.push({ source: `discovery:browser:${COMPANY}`, url: l.href, title, company: COMPANY,
                 location, description: text.slice(0, 12000), source_is_origin: true });
    } catch (e) { /* skip postings that fail to load */ }
  }
  return out;
}
