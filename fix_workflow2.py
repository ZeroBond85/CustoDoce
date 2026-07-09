import re

with open('C:/Zerobond/Code/CustoDoce/.github/workflows/teste_full_manual.yml', 'r') as f:
    content = f.read()

# Replace the broken integration block
old = '''      - if: steps.pw-cache.outputs.cache-hit != 'true'
      - run: echo "CI_JOB_START=$(date +%s)" >> $GITHUB_ENV
      - run: python -m pytest tests/integration/ -q --tb=short --no-header --durations=5
        env:
        if: always()
        name: Install Playwright
        run: python -m playwright install chromium --with-deps'''

new = '''      - if: steps.pw-cache.outputs.cache-hit != 'true'
        name: Install Playwright browsers
        run: python -m playwright install chromium --with-deps
      - run: echo "CI_JOB_START=$(date +%s)" >> $GITHUB_ENV
      - run: python -m pytest tests/integration/ -q --tb=short --no-header --durations=5'''

if 'if: always()' in content and 'name: Install Playwright' in content:
    content = content.replace(
        '''      - if: steps.pw-cache.outputs.cache-hit != 'true'
      - run: echo "CI_JOB_START=$(date +%s)" >> $GITHUB_ENV
      - run: python -m pytest tests/integration/ -q --tb=short --no-header --durations=5
        env:
        if: always()
        name: Install Playwright
        run: python -m playwright install chromium --with-deps''',
        '''      - if: steps.pw-cache.outputs.cache-hit != 'true'
        name: Install Playwright browsers
        run: python -m playwright install chromium --with-deps
      - run: echo "CI_JOB_START=$(date +%s)" >> $GITHUB_ENV
      - run: python -m pytest tests/integration/ -q --tb=short --no-header --durations=5''')
    with open('C:/Zerobond/Code/CustoDoce/.github/workflows/teste_full_manual.yml', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('Pattern not found')
    # Find the context
    idx = content.find('if: always()')
    if idx > 0:
        print(content[max(0,idx-300):idx+300])