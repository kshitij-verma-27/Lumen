from pathlib import Path
import re

# 1. Fix style.css
css_path = Path("frontend/style.css")
css = css_path.read_text(encoding="utf-8")

# Replace any occurrence of --font-sans with Atkinson Hyperlegible
css = re.sub(
    r"--font-sans:\s*['\"]Inter['\"],[^;]+;",
    "--font-sans: 'Atkinson Hyperlegible', 'Noto Sans', 'Noto Sans Devanagari', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
    css
)

# Contrast fixes for buttons and badges in Dark and High-Contrast
contrast_rules = """
/* Button High-Contrast Overrides */
[data-theme="dark"] .btn-composer-send,
[data-theme="dark"] .notion-btn-primary {
  background: #8AB4F8 !important;
  color: #121212 !important;
  border-color: #8AB4F8 !important;
  font-weight: 600 !important;
}

[data-theme="high-contrast"] .btn-composer-send,
[data-theme="high-contrast"] .notion-btn-primary {
  background: #FFFF00 !important;
  color: #000000 !important;
  border: 2px solid #FFFFFF !important;
  font-weight: 700 !important;
}

/* Badge Contrast Overrides: Ensure >= 7:1 in all themes */
[data-theme="light"] .signal-badge.amber,
[data-theme="light"] .badge-amber {
  background: #FEF3C7 !important;
  color: #6A2C08 !important;
  border-color: #6A2C08 !important;
}

[data-theme="light"] .signal-badge.sage,
[data-theme="light"] .badge-sage,
[data-theme="light"] .badge-official {
  background: #E6F4EA !important;
  color: #134E28 !important;
  border-color: #134E28 !important;
}

[data-theme="light"] .signal-badge.blue,
[data-theme="light"] .badge-blue {
  background: #E0F2FE !important;
  color: #034D74 !important;
  border-color: #034D74 !important;
}

[data-theme="dark"] .signal-badge.amber,
[data-theme="dark"] .badge-amber {
  background: #3B2606 !important;
  color: #FFF0B3 !important;
  border-color: #FFF0B3 !important;
}

[data-theme="dark"] .signal-badge.sage,
[data-theme="dark"] .badge-sage,
[data-theme="dark"] .badge-official {
  background: #153223 !important;
  color: #D1F8DD !important;
  border-color: #D1F8DD !important;
}

[data-theme="high-contrast"] .signal-badge,
[data-theme="high-contrast"] .badge {
  border: 2px solid #FFFFFF !important;
  color: #FFFFFF !important;
}
[data-theme="high-contrast"] .signal-badge.amber {
  color: #FFFF00 !important;
  border-color: #FFFF00 !important;
}
"""

css += "\n" + contrast_rules
css_path.write_text(css, encoding="utf-8")

# 2. Fix app.js badge text
app_path = Path("frontend/app.js")
app_js = app_path.read_text(encoding="utf-8")

# Fix badge_text
app_js = app_js.replace(
    'const indText = `${indCount} source${indCount !== 1 ? \'s\' : \'\'}, ${origCount} original`;',
    'const indText = indData?.badge_text || `${indCount} source${indCount !== 1 ? \'s\' : \'\'}, ${typeof origCount === \'number\' ? origCount : (indData?.independent_sources || 1)} original`;'
)

app_path.write_text(app_js, encoding="utf-8")

print("Successfully updated font stack and contrast rules in style.css and app.js")
