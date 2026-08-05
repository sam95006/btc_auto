/** Skip link for keyboard users — first focusable in document order. */
export function SkipToContent() {
  return (
    <a className="nx-skip-link" href="#main-content">
      {/* label filled by parent via children or i18n at call site */}
    </a>
  );
}

export function SkipToContentLabeled({ label }: { label: string }) {
  return (
    <a className="nx-skip-link" href="#main-content">
      {label}
    </a>
  );
}
