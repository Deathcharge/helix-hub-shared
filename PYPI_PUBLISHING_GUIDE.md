# PyPI Publishing Guide for helix-llm-agent-engine

This guide walks you through publishing the helix-llm-agent-engine package to PyPI so users can install it with `pip install helix-llm-agent-engine`.

## Prerequisites

1. **PyPI Account** - Create one at https://pypi.org/account/register/
2. **TestPyPI Account** (optional but recommended) - https://test.pypi.org/account/register/
3. **Python 3.8+** installed locally
4. **Build tools** installed:
   ```bash
   pip install --upgrade pip setuptools wheel twine
   ```

## Step-by-Step Publishing Process

### Step 1: Prepare Your Local Environment

```bash
# Clone the repository locally
git clone https://github.com/Deathcharge/helix-hub-shared.git helix-llm-agent-engine
cd helix-llm-agent-engine

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install --upgrade pip setuptools wheel twine
```

### Step 2: Verify Package Structure

Ensure your repository has:
- ✅ `setup.py` - Package metadata and configuration
- ✅ `README.md` - Package description
- ✅ `LICENSE` - MIT license file
- ✅ `requirements.txt` - Dependencies
- ✅ `.gitignore` - Exclude unnecessary files
- ✅ `helix_llm_agent_engine/` - Main package directory with `__init__.py`

```bash
# Verify structure
ls -la
# Should show: setup.py, README.md, LICENSE, requirements.txt, helix_llm_agent_engine/
```

### Step 3: Update Version Number

Edit `setup.py` and increment the version:

```python
setup(
    name="helix-llm-agent-engine",
    version="0.1.0",  # Increment this: 0.1.0 → 0.1.1 → 0.2.0, etc.
    ...
)
```

### Step 4: Build the Distribution Package

```bash
# Clean previous builds
rm -rf build dist *.egg-info

# Build wheel and source distribution
python setup.py sdist bdist_wheel

# Verify build
ls -la dist/
# Should show: helix_llm_agent_engine-0.1.0-py3-none-any.whl and helix_llm_agent_engine-0.1.0.tar.gz
```

### Step 5: Test on TestPyPI (Recommended)

```bash
# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# When prompted, enter your TestPyPI credentials
# Username: __token__
# Password: Your TestPyPI API token (from https://test.pypi.org/manage/account/tokens/)

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ helix-llm-agent-engine
```

### Step 6: Publish to PyPI

```bash
# Upload to official PyPI
twine upload dist/*

# When prompted, enter your PyPI credentials
# Username: __token__
# Password: Your PyPI API token (from https://pypi.org/manage/account/tokens/)
```

### Step 7: Verify Publication

```bash
# Install from PyPI
pip install helix-llm-agent-engine

# Test import
python -c "from helix_llm_agent_engine import LLMAgentEngine; print('✅ Successfully installed!')"
```

## Using PyPI API Tokens (Recommended for Security)

Instead of using your PyPI password:

1. Go to https://pypi.org/manage/account/tokens/
2. Click "Add API token"
3. Give it a name (e.g., "helix-llm-agent-engine")
4. Copy the token
5. When prompted by twine, use:
   - Username: `__token__`
   - Password: Paste your token

## Automating with GitHub Actions (Optional)

Create `.github/workflows/publish-to-pypi.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [created]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install setuptools wheel twine
      - name: Build distribution
        run: python setup.py sdist bdist_wheel
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

Then add your PyPI API token as a GitHub secret named `PYPI_API_TOKEN`.

## Troubleshooting

### "Invalid distribution" error
- Ensure `setup.py` is valid: `python setup.py check`
- Check that all required fields are present in `setup.py`

### "File already exists" error
- You can't re-upload the same version
- Increment the version number in `setup.py`
- Rebuild and upload again

### "Unauthorized" error
- Verify your PyPI credentials are correct
- Check that your API token hasn't expired
- Generate a new token if needed

## Next Steps

After publishing:

1. **Announce Release** - Post on GitHub, Discord, Twitter
2. **Update Documentation** - Add installation instructions
3. **Create Changelog** - Document what changed in this version
4. **Monitor Downloads** - Check PyPI stats at https://pypi.org/project/helix-llm-agent-engine/

## Resources

- PyPI Documentation: https://packaging.python.org/
- setuptools Guide: https://setuptools.pypa.io/
- twine Documentation: https://twine.readthedocs.io/
- Semantic Versioning: https://semver.org/

---

**Version:** 1.0  
**Last Updated:** 2026-01-28  
**Maintained by:** Helix Collective
