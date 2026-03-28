# rbcopy



## Developer Documentation

Comprehensive developer documentation is available in [`docs/dev/`](./docs/dev/) covering testing, configuration, deployment, and all project features.

### Quick Start for Developers

```bash
# Install development environment
make install

# Run tests
make tests

# Auto-fix formatting
make chores
```

See the [developer documentation](./docs/dev/README.md) for complete guides and reference.


Next, run your build command:
Now, when you want to build a specific version, you pass that variable to the terminal right before you run PyInstaller. The exact command depends on the terminal you are using:

If you are using Windows PowerShell:
$env:EXE_NAME="rbcopy-v0.2.0"; pyinstaller rbcopy.spec

If you are using standard Windows Command Prompt (CMD):
set EXE_NAME=rbcopy-v0.2.0 && pyinstaller rbcopy.spec

If you are using Git Bash / Linux / Mac:
EXE_NAME=rbcopy-v0.2.0 pyinstaller rbcopy.spec