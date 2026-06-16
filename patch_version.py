import sys, re
sys.path.insert(0, '.')
from version import APP_VERSION
with open('installer.iss', 'r') as f:
    s = f.read()
s = re.sub(r'#define MyAppVersion "[^"]+"', '#define MyAppVersion "' + APP_VERSION + '"', s)
with open('installer.iss', 'w') as f:
    f.write(s)
with open('_ver.txt', 'w') as f:
    f.write(APP_VERSION)
print('Version: ' + APP_VERSION)
print('Patched installer.iss')
