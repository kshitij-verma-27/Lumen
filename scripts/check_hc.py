from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8000/')
    page.evaluate("document.documentElement.setAttribute('data-theme', 'high-contrast')")
    data = page.evaluate("""() => {
        const bodyCS = window.getComputedStyle(document.body);
        const h1 = document.querySelector('h1');
        const h1CS = h1 ? window.getComputedStyle(h1) : null;
        const p = document.querySelector('p');
        const pCS = p ? window.getComputedStyle(p) : null;
        const link = document.querySelector('a');
        const linkCS = link ? window.getComputedStyle(link) : null;
        return {
            bodyColor: bodyCS.color,
            bodyBg: bodyCS.backgroundColor,
            h1Color: h1CS ? h1CS.color : null,
            pColor: pCS ? pCS.color : null,
            linkColor: linkCS ? linkCS.color : null
        };
    }""")
    print("DATA:", data)
    browser.close()
