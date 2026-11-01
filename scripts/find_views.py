with open('frontend/index.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'id=' in line and 'view' in line.lower():
            print(f"{i}: {line.strip()}")
