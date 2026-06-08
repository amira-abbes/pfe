import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export default function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  labelledBy = "platform-drawer-title",
}) {
  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="platform-drawer-layer">
      <button className="platform-drawer-overlay" onClick={onClose} aria-label="Fermer le panneau" />
      <aside className="platform-drawer" role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        <header className="platform-drawer-header">
          <div>
            <h2 id={labelledBy}>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button className="platform-drawer-close" onClick={onClose} aria-label="Fermer">
            <X size={20} />
          </button>
        </header>
        <div className="platform-drawer-body">{children}</div>
        {footer && <footer className="platform-drawer-footer">{footer}</footer>}
      </aside>
    </div>,
    document.body
  );
}
