// Run by the careers-browser agent via browser_evaluate on a careers listing page.
// Replace __LINK_PATTERN__ and __COMPANY__ before use. Returns posting objects in the Posting schema.
// Descriptions are fetched from each posting page inside the browser (same site, same session).
async () => {
  const LINK_PATTERN = "__LINK_PATTERN__";
  const COMPANY = "__COMPANY__";
  const RELEVANT = /machine learning|\bML\b|\bAI\b|data scien|NLP|LLM|deep learning|computer vision|graduate|junior|entry/i;
  // Some lists render late (DataArt ~10 s): scroll and wait up to 15 s for posting links to appear.
  for (let i = 0; i < 15 && !document.querySelector(`a[href*="${LINK_PATTERN}"]`); i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 1000));
  }
  const seen = new Set();
  // Title: the link's first line of text; links without text (DataArt cards) use their card's first line.
  const titleOf = a => {
    const firstLine = el => ((el && el.innerText) || "").split("\n").map(s => s.trim()).find(Boolean) || "";
    return firstLine(a) || firstLine(a.closest("article, li") || a.parentElement);
  };
  const links = [...document.querySelectorAll(`a[href*="${LINK_PATTERN}"]`)]
    .map(a => ({ text: titleOf(a), href: a.href.split("?")[0] }))
    .filter(l => l.text && RELEVANT.test(l.text) && !seen.has(l.href) && seen.add(l.href))
    .slice(0, 15);
  // Render a same-site posting page in a hidden frame and read its text once the posting itself has
  // rendered: its title is present and there is more than navigation (up to 15 s).
  const renderedText = async (href, title) => {
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:absolute;width:1200px;height:900px;left:-5000px";
    frame.src = href;
    document.body.appendChild(frame);
    let text = "";
    for (let i = 0; i < 15; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try { text = (frame.contentDocument.body.innerText || "").trim(); } catch (e) { break; }
      if (text.includes(title) && text.length > 2000) break;
    }
    frame.remove();
    return text.replace(/\n\s*\n+/g, "\n");
  };
  const out = [];
  for (const l of links) {
    try {
      const html = await (await fetch(l.href)).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      doc.querySelectorAll("script,style,nav,footer,header,svg").forEach(e => e.remove());
      // A page that is not displayed has no layout, so textContent glues paragraphs together
      // ("…00-843SummaryAndersen is hiring…"). Mark block ends so sentences stay separate.
      doc.querySelectorAll("p,li,div,h1,h2,h3,h4,h5,h6,br,tr,section,article,ul,ol").forEach(e => e.append("\n"));
      let text = ((doc.querySelector("main") || doc.body).textContent || "").replace(/[ \t]+/g, " ").replace(/\s*\n\s*/g, "\n").trim();
      const shortTitle = l.text.split(/ Office:| Remote:| \| | Andersen is hiring/)[0].trim();
      if (text.length < 800 || !text.includes(shortTitle)) {  // JavaScript-rendered posting (DataArt)
        text = (await renderedText(l.href, shortTitle)) || text;
      }
      const title = l.text.split(/ Office:| Remote:| \| | Andersen is hiring/)[0].trim();
      const location = (l.text.match(/(Office|Remote):.*/) || [""])[0];
      out.push({ source: `discovery:browser:${COMPANY}`, url: l.href, title, company: COMPANY,
                 location, description: text.slice(0, 12000), source_is_origin: true });
    } catch (e) { /* skip postings that fail to load */ }
  }
  return out;
}
