import re

with open('C:/Users/negr1/Projeler/ACCIO-JARVIS/study_ref/bundle.js', 'r', encoding='utf-8') as f:
    js = f.read()

pos = js.find('acct__signin')
if pos != -1:
    print(js[pos-100:pos+800].replace('\n', ' '))
