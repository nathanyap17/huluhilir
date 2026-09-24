import os
files = ['demo_farm.json', 'knowledge_docs.json', 'templates.json']
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        data = file.read()
    data = data.replace('HuluHilir', 'PepperDex')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(data)
