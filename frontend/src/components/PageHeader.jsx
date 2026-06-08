export default function PageHeader({ eyebrow, title, subtitle, action, className = "" }) {
  return (
    <header className={`platform-page-header ${className}`.trim()}>
      <div className="platform-page-header-copy">
        {eyebrow && <span className="platform-page-eyebrow">{eyebrow}</span>}
        <h1 className="platform-page-title">{title}</h1>
        {subtitle && <p className="platform-page-subtitle">{subtitle}</p>}
      </div>
      {action && <div className="platform-page-actions">{action}</div>}
    </header>
  );
}
