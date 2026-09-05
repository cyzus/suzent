"""Bounded DOM observation, retaining node identity separately from labels."""

CONTROLS_READY_SCRIPT = """
() => Array.from(document.querySelectorAll(
    'a, button, input, textarea, select, [role="button"], [role="link"], [contenteditable="true"]'
)).some(el => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
})
"""

SNAPSHOT_SCRIPT = r"""
({offset, limit, interactiveOnly}) => {
    const visible = el => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 &&
            style.visibility !== 'hidden' && style.display !== 'none';
    };
    const label = el => {
        const editable = el.matches('input, textarea, select, [contenteditable]');
        return (el.getAttribute('aria-label') ||
            Array.from(el.labels || []).map(label => label.innerText).join(' ') ||
            el.getAttribute('placeholder') || (editable ? '' : el.innerText) || '')
            .replace(/\s+/g, ' ').slice(0, 120);
    };
    const elements = Array.from(document.querySelectorAll(
        'a, button, input, textarea, select, [role="button"], [role="link"], [contenteditable="true"]'
    )).filter(visible);
    const nodes = elements.slice(offset, offset + limit);
    const items = nodes.map(el => ({
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type'), href: el.getAttribute('href'), name: el.getAttribute('name'),
        label: label(el),
        disabled: el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true'
    }));
    let text = '';
    if (!interactiveOnly && document.body) {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode() && text.length < 4001) {
            const node = walker.currentNode;
            const parent = node.parentElement;
            if (!parent || parent.closest('script, style, noscript, input, textarea, select, [contenteditable]') ||
                !visible(parent)) continue;
            const part = node.textContent.replace(/\s+/g, ' ').trim();
            if (part) text += part.slice(0, 4001 - text.length) + '\n';
        }
    }
    return {nodes, data: {
        items, url: location.href, title: document.title, ready_state: document.readyState,
        total: elements.length, text: text.slice(0, 4000), text_truncated: text.length > 4000,
        frame_count: document.querySelectorAll('iframe, frame').length
    }};
}
"""

ELEMENT_STATE_SCRIPT = """
el => ({connected: el.isConnected, tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'), href: el.getAttribute('href'), name: el.getAttribute('name'), label: (
        el.getAttribute('aria-label') ||
        Array.from(el.labels || []).map(label => label.innerText).join(' ') ||
        el.getAttribute('placeholder') ||
        (el.matches('input, textarea, select, [contenteditable]') ? '' : el.innerText) || ''
    ).replace(/\\s+/g, ' ').slice(0, 120)})
"""
