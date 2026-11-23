import re, json

with open('C:/Users/negr1/Projeler/ACCIO-JARVIS/study_ref/bundle.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Search for Rose, Lavender, Sage, Mommy images or portrait definitions
for word in ['Sage', 'Lavender', 'Rose', 'Winter attic', 'office', 'portrait', 'avatar']:
    matches = [m.start() for m in re.finditer(re.escape(word), js)]
    print(f"Occurrences of '{word}': {len(matches)}")
    for pos in matches[:3]:
        snippet = js[max(0, pos-100):min(len(js), pos+200)]
        print(f"--- Snippet for {word} at {pos} ---")
        print(snippet.replace('\n', ' '))
