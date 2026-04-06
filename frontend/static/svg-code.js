/**
 * Adds "View Code" buttons to SVG previews.
 * Call addCodeButton(container) after inserting SVG HTML into a .svg-preview element.
 * Or call addCodeButtons() to add buttons to all .svg-preview elements on the page.
 */

function addCodeButton(container) {
    if (!container || container.querySelector('.svg-code-btn')) return;
    const svg = container.querySelector('svg');
    if (!svg) return;

    const btn = document.createElement('button');
    btn.className = 'svg-code-btn';
    btn.textContent = '</>';
    btn.title = 'View SVG code';

    const codeWrap = document.createElement('div');
    codeWrap.className = 'svg-code-wrap';
    codeWrap.style.display = 'none';

    const pre = document.createElement('pre');
    const code = document.createElement('code');
    pre.appendChild(code);
    codeWrap.appendChild(pre);

    const copyBtn = document.createElement('button');
    copyBtn.className = 'svg-code-copy';
    copyBtn.textContent = 'Copy';
    codeWrap.appendChild(copyBtn);

    container.after(codeWrap);

    btn.addEventListener('click', () => {
        const isOpen = codeWrap.style.display !== 'none';
        if (!isOpen) {
            // Grab fresh SVG source
            const svgEl = container.querySelector('svg');
            if (svgEl) code.textContent = svgEl.outerHTML;
            codeWrap.style.display = 'block';
            btn.classList.add('active');
        } else {
            codeWrap.style.display = 'none';
            btn.classList.remove('active');
        }
    });

    copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(code.textContent).then(() => {
            copyBtn.textContent = 'Copied!';
            setTimeout(() => copyBtn.textContent = 'Copy', 1500);
        });
    });

    container.appendChild(btn);
}

function addCodeButtons() {
    document.querySelectorAll('.svg-preview').forEach(addCodeButton);
}
