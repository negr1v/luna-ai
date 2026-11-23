import re

with open('C:/Users/negr1/Projeler/ACCIO-JARVIS/study_ref/bundle.js', 'r', encoding='utf-8') as f:
    js = f.read()

for phrase in ['Sign in', 'Sign up', 'Log in', 'account', 'email']:
    matches = [m.start() for m in re.finditer(re.escape(phrase), js)]
    print(f"Phrase '{phrase}': {len(matches)} matches")
    for pos in matches[:2]:
        print("  ...", js[max(0, pos-60):min(len(js), pos+120)].replace('\n', ' '), "...")
