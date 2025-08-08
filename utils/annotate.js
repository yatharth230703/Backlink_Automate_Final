const customCSS = `
  ::-webkit-scrollbar { width: 10px; }
  ::-webkit-scrollbar-track { background: #27272a; }
  ::-webkit-scrollbar-thumb { background: #888; border-radius: 0.375rem; }
  ::-webkit-scrollbar-thumb:hover { background: #555; }
`;
document.head.append(Object.assign(document.createElement('style'), { textContent: customCSS }));

const BOX_CLASS = '__ai-annot';
const LABEL_CLASS = '__ai-label';

function unmarkPage() {
  document.querySelectorAll('.' + BOX_CLASS).forEach(el => el.remove());
  document.querySelectorAll('.' + LABEL_CLASS).forEach(el => el.remove());
}

function getBestLabelPosition(r, labelWidth = 30, labelHeight = 20) {
  if (!r || typeof r.left === 'undefined' || typeof r.top === 'undefined' || 
      typeof r.right === 'undefined' || typeof r.bottom === 'undefined') {
    return { x: 0, y: 0 }; // fallback position
  }
  
  const vw = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);

  const options = [
    { name: 'top-left', x: r.left - 2, y: r.top - labelHeight - 2 },
    { name: 'top-right', x: r.right - labelWidth, y: r.top - labelHeight - 2 },
    { name: 'bottom-left', x: r.left - 2, y: r.bottom + 2 },
    { name: 'bottom-right', x: r.right - labelWidth, y: r.bottom + 2 }
  ];

  return options
    .map(pos => ({
      ...pos,
      visible: pos.x >= 0 && pos.y >= 0 && pos.x + labelWidth <= vw && pos.y + labelHeight <= vh,
      distance: Math.hypot((r.left + r.width / 2) - (pos.x + labelWidth / 2), (r.top + r.height / 2) - (pos.y + labelHeight / 2))
    }))
    .filter(pos => pos.visible)
    .sort((a, b) => a.distance - b.distance)[0] || options[0];  // fallback
}

// Generate visually safe colors using HSL
function randColor() {
  const hue = Math.floor(Math.random() * 360);
  const saturation = 70;
  const lightness = 40;
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}

function markPage() {
  unmarkPage();

  const vw = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);

  const allElements = Array.from(document.querySelectorAll('*')).map(element => {
    const text = element.textContent.trim().replace(/\s{2,}/g, ' ');
    const type = element.tagName.toLowerCase();
    const ariaLabel = element.getAttribute('aria-label') || '';
    const rects = [...element.getClientRects()]
      .filter(bb => {
        const cx = bb.left + bb.width / 2, cy = bb.top + bb.height / 2;
        const elAt = document.elementFromPoint(cx, cy);
        return elAt === element || element.contains(elAt);
      })
      .map(bb => {
        const left = Math.max(0, bb.left),
          top = Math.max(0, bb.top),
          right = Math.min(vw, bb.right),
          bottom = Math.min(vh, bb.bottom);
        return {
          left, top, right, bottom,
          width: right - left, height: bottom - top
        };
      });
    const area = rects.reduce((s, r) => s + r.width * r.height, 0);

    const inputType = element.getAttribute('type');
    const isSmallInput = type === 'input' && ['checkbox', 'radio'].includes(inputType);

    const include =
      (
        ['input', 'span', 'textarea', 'select', 'button', 'a', 'iframe', 'video'].includes(type)
        || element.onclick != null
        || getComputedStyle(element).cursor === 'pointer'
      )
      && (
        area >= 20 || isSmallInput
      );

    return { element, rects, type, text, ariaLabel, include };
  });

  const included = allElements.filter(item => item.include);
  const items = included.filter(x => !included.some(y => y.element !== x.element && y.element.contains(x.element)));

  items.forEach((item, idx) => {
    item.id = idx;
    const elem = item.element;
    const color = randColor();

    // Draw box
    item.rects.forEach(r => {
      const box = document.createElement('div');
      Object.assign(box.style, {
        outline: `2px dashed ${color}`,
        position: 'fixed',
        left: `${r.left}px`,
        top: `${r.top}px`,
        width: `${r.width}px`,
        height: `${r.height}px`,
        pointerEvents: 'none',
        boxSizing: 'border-box',
        zIndex: 2147483646
      });
      box.classList.add(BOX_CLASS);
      document.body.appendChild(box);
    });

    // Label
    const r = item.rects[0];
    if (!r) return; // Skip if no valid rect
    const lbl = document.createElement('span');
    lbl.textContent = idx;

    const labelPos = getBestLabelPosition(r);
    Object.assign(lbl.style, {
      position: 'fixed',
      top: `${labelPos.y}px`,
      left: `${labelPos.x}px`,
      background: color,
      color: '#fff',
      padding: '2px 4px',
      fontSize: '12px',
      borderRadius: '2px',
      zIndex: 2147483647,
      pointerEvents: 'none'
    });

    lbl.classList.add(LABEL_CLASS);
    document.body.appendChild(lbl);
  });

  return items.flatMap(item =>
    item.rects.map(r => {
      const elem = item.element;
      const label = elem.labels?.[0]?.innerText || '';
      return {
        id: item.id,
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
        tag: item.type,
        text: item.text,
        ariaLabel: item.ariaLabel || '',
        placeholder: elem.getAttribute('placeholder') || '',
        name: elem.getAttribute('name') || '',
        typeAttr: elem.getAttribute('type') || '',
        idAttr: elem.getAttribute('id') || '',
        classAttr: elem.className || '',
        labelText: label,
        isVisible: !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length),
        bbox: {
          left: r.left,
          top: r.top,
          width: r.width,
          height: r.height
        }
      };
    })
  );
}
