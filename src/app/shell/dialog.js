/**
 * ============================================================================
 * IN-APP CONFIRMATION DIALOG
 * ============================================================================
 * Replaces the native `alert()` / `confirm()` calls. A blocking native dialog
 * inside a single page app kills the flow, and `alert()` cannot be styled or
 * announced properly.
 * ============================================================================
 */

/**
 * Escapes text before it is injected into markup.
 * @param {string} value
 * @returns {string}
 */
function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (char) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[char]
  );
}

/* ==========================================================================
 * THE SHARED MODAL CHOREOGRAPHY
 * ==========================================================================
 * Every modal of the app — the preferences, the URL import, the translation
 * and the version history — is a backdrop element that carries the `hidden`
 * attribute, with the dialog card sitting inside it. Each one used to
 * hand-roll the same routine: show, move the focus in, close on a backdrop
 * click or on Escape, hide again and give the focus back. The routine lives
 * here now, once — and the registry is the one place that answers the
 * question "is a modal open right now?".
 * ==========================================================================
 */

/**
 * The known modals, keyed by their backdrop element. An entry holds what is
 * particular to one modal: where the focus goes back to when it closes,
 * what a close has to undo besides hiding, and whether Escape is spoken for
 * by a dialog that sits on top of it.
 * @type {Map<HTMLElement, {
 *   previousFocus: Element|null,
 *   getRestoreTarget: ((previousFocus: Element|null) => Element|null)|null,
 *   onClose: (() => void)|null,
 *   escapeGuard: (() => boolean)|null
 * }>}
 */
const modalRegistry = new Map();

/**
 * The entry of a modal, made on first sight.
 * @param {HTMLElement} element
 * @returns {{previousFocus: Element|null, getRestoreTarget: ((previousFocus: Element|null) => Element|null)|null, onClose: (() => void)|null, escapeGuard: (() => boolean)|null}}
 */
function modalEntry(element) {
  let entry = modalRegistry.get(element);
  if (!entry) {
    entry = { previousFocus: null, getRestoreTarget: null, onClose: null, escapeGuard: null };
    modalRegistry.set(element, entry);
  }
  return entry;
}

/** Whether the one Escape listener of the modals is on the window already. */
let modalEscapeWired = false;

/**
 * One Escape listener for every modal: each open one closes, unless its own
 * guard says that a dialog sitting on top of it is speaking for the key.
 */
function wireModalEscape() {
  if (modalEscapeWired) return;
  modalEscapeWired = true;
  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;

    for (const [element, entry] of modalRegistry) {
      if (element.hasAttribute('hidden')) continue;
      // A confirmation the modal itself opened is on top: the Escape key
      // answers that dialog, and the modal stays where it is.
      if (entry.escapeGuard && entry.escapeGuard()) continue;
      closeModal(element);
    }
  });
}

/**
 * Puts a modal under the shared choreography: a click on the backdrop and
 * the Escape key close it, and the registry learns about it. The options
 * are what differs from modal to modal — not every one gives the focus
 * back, and some keep their door shut while a confirmation of their own is
 * open.
 *
 * @param {HTMLElement} element the backdrop element
 * @param {object} [options]
 * @param {((previousFocus: Element|null) => Element|null)} [options.getRestoreTarget]
 *   where the focus goes back to when the modal closes
 * @param {(() => void)} [options.onClose] what a close has to undo besides hiding
 * @param {(() => boolean)} [options.escapeGuard] whether Escape belongs to a
 *   dialog on top of the modal right now
 * @returns {() => void} takes the modal out of the registry again
 */
export function registerModal(
  element,
  { getRestoreTarget = null, onClose = null, escapeGuard = null } = {}
) {
  if (!element) return () => {};

  const entry = modalEntry(element);
  entry.getRestoreTarget = getRestoreTarget;
  entry.onClose = onClose;
  entry.escapeGuard = escapeGuard;

  // The backdrop click: a click that lands on the backdrop itself, not on
  // the card that sits inside it.
  element.addEventListener('click', (event) => {
    if (event.target === element) closeModal(element);
  });

  wireModalEscape();

  return () => {
    modalRegistry.delete(element);
  };
}

/**
 * Shows a modal: takes the `hidden` attribute off, remembers where the
 * focus came from, and moves the focus into the dialog so keyboard and
 * screen-reader users are not left behind on the page behind the modal.
 *
 * @param {HTMLElement|null} element the backdrop element
 * @param {object} [options]
 * @param {Element|null} [options.focusTarget] the control the focus moves into
 * @param {(() => void)} [options.onOpen] what runs once the modal is shown,
 *   before the focus moves in
 * @returns {boolean} whether the modal was opened
 */
export function openModal(element, { focusTarget = null, onOpen = null } = {}) {
  if (!element) return false;

  const entry = modalEntry(element);
  entry.previousFocus = document.activeElement;

  element.removeAttribute('hidden');
  if (onOpen) onOpen();

  if (focusTarget && typeof focusTarget.focus === 'function') focusTarget.focus();
  return true;
}

/**
 * Hides a modal and gives the focus back — when the modal has said where
 * the focus goes; not every one does.
 *
 * @param {HTMLElement|null} element the backdrop element
 * @returns {boolean} whether the modal was closed
 */
export function closeModal(element) {
  if (!element) return false;

  const entry = modalRegistry.get(element);
  element.setAttribute('hidden', '');

  if (entry?.onClose) entry.onClose();

  const previousFocus = entry ? entry.previousFocus : null;
  if (entry) entry.previousFocus = null;

  const target = entry?.getRestoreTarget ? entry.getRestoreTarget(previousFocus) : null;
  if (target && typeof target.focus === 'function') {
    try {
      target.focus();
    } catch {
      /* the element may be gone already */
    }
  }
  return true;
}

/**
 * Whether a modal that handles its own Escape key is open right now — the
 * question the keyboard shortcuts ask before Escape does something else.
 * @returns {boolean}
 */
export function isModalHandlingEscape() {
  for (const element of modalRegistry.keys()) {
    if (!element.hasAttribute('hidden')) return true;
  }
  return false;
}

/**
 * Whether any modal surface is open — the `hidden`-attribute modals and the
 * native confirmation dialogs alike.
 * @returns {boolean}
 */
export function isModalOpen() {
  return isModalHandlingEscape() || Boolean(document.querySelector('dialog[open]'));
}

/**
 * Shows a modal confirmation dialog.
 * @param {{ title: string, message: string, confirmLabel?: string, cancelLabel?: string, danger?: boolean }} options
 * @returns {Promise<boolean>}
 */
export function confirmDialog({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false
}) {
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'app-dialog';
    dialog.innerHTML = `
      <div class="modal-card max-w-sm">
        <div class="modal-header">
          <div class="modal-title"><h3>${escapeHtml(title)}</h3></div>
        </div>
        <div class="modal-body">
          <p class="text-sm leading-relaxed text-fg-2">${escapeHtml(message)}</p>
        </div>
        <div class="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" class="btn btn-sm" data-role="cancel">${escapeHtml(cancelLabel)}</button>
          <button type="button" class="btn btn-sm ${danger ? 'btn-danger' : 'btn-primary'}" data-role="confirm">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>
    `;

    document.body.appendChild(dialog);

    let settled = false;
    const done = (value) => {
      if (settled) return;
      settled = true;
      dialog.close();
      dialog.remove();
      resolve(value);
    };

    dialog.querySelector('[data-role="cancel"]').addEventListener('click', () => done(false));
    dialog.querySelector('[data-role="confirm"]').addEventListener('click', () => done(true));
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      done(false);
    });

    dialog.showModal();
  });
}
