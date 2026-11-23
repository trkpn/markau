/**
 * ============================================================================
 * PRINTING
 * ============================================================================
 *
 * The browser's print dialog is the app's PDF exporter: it prints the
 * *rendered* document — diagrams, callouts and footnotes included — not the
 * Markdown source.
 *
 * The print stylesheet (see `style.css`) hides the application chrome and
 * prints the preview alone, in ink-friendly colours.
 * ============================================================================
 */

import { el } from '@/app/shell/dom.js';
import { getSettings } from '@/core/settings.js';
import { getDocumentMeta } from '@/markdown/parser.js';
import { prepareMermaidForPrint } from '@/markdown/mermaid.js';
import { flushRender } from '@/app/preview/preview.js';

const PRINT_PAGE_STYLE_ID = 'ma-print-page-style';

/**
 * Applies the user's chosen A4 orientation (portrait or landscape) via a
 * temporary `@page` rule and root attribute, returning a cleanup callback.
 * @returns {() => void}
 */
function applyPrintOrientation() {
  const orientation = getSettings().printOrientation === 'landscape' ? 'landscape' : 'portrait';
  const margin = orientation === 'landscape' ? '12mm 14mm' : '14mm 14mm';

  document.documentElement.dataset.printOrientation = orientation;

  let style = document.getElementById(PRINT_PAGE_STYLE_ID);
  if (!style) {
    style = document.createElement('style');
    style.id = PRINT_PAGE_STYLE_ID;
    document.head.appendChild(style);
  }
  style.textContent = `@page { size: A4 ${orientation}; margin: ${margin}; }`;

  return () => {
    delete document.documentElement.dataset.printOrientation;
    style.remove();
  };
}

/** The name of the app — the fallback title of a printed document. */
const APP_TITLE = 'MarkAu';

/**
 * The title of the document: the front matter, the first heading, or the
 * name of the app.
 * @returns {string}
 */
export function getDocumentTitle() {
  const meta = getDocumentMeta(el.editor.value);
  if (meta.title) return meta.title;

  const heading = el.editor.value.split('\n').find((line) => line.startsWith('# '));
  return heading ? heading.slice(2).trim() : APP_TITLE;
}

/**
 * Prints the current document.
 */
export async function printDocument() {
  // The preview has to be current, or the printout shows an older version.
  await flushRender();
  const restoreMermaid = await prepareMermaidForPrint(el.preview);
  const restoreOrientation = applyPrintOrientation();

  const previous = document.title;
  const title = getDocumentTitle();
  if (title) document.title = title;

  let restored = false;
  const restore = () => {
    if (restored) return;
    restored = true;
    document.title = previous;
    restoreOrientation();
    restoreMermaid();
  };

  window.addEventListener('afterprint', restore, { once: true });
  window.print();

  // Not every browser fires `afterprint` — the title has to come back
  // either way.
  setTimeout(restore, 2000);
}
