## Description
## AI Agent & Developer Checklist
### Architecture & Style
- [ ] I have prioritized `async` libraries and functions over synchronous ones where applicable.
- [ ] I have not used `print()` for logging/debugging; I used the `getLogger(__name__)` logger.
- [ ] I have handled exceptions properly and used `logger.exception` when suppressing them.
- [ ] Filenames are strictly lowercase.

### Typing & Data Structures
- [ ] ALL function signatures, returns, and variables are fully typed.
- [ ] I have avoided using `Any` unless absolutely necessary.
- [ ] I have used `dataclass` or Pydantic models with typed parameters instead of generic `dict`s.
- [ ] I used `Type | None` instead of `Optional[Type]`.

### Configuration & Dependencies
- [ ] Any new settings were added to `rbcopy/conf/settings.py` using `pydantic-settings`.
- [ ] Sensitive configuration data uses `SecretStr` or `SecretBytes`.
- [ ] All new dependencies are defined in `pyproject.toml` (No `setup.py` or `setup.cfg`).

### Testing
- [ ] I have added or updated tests to cover the new code.
- [ ] I used single test functions instead of wrapping them in classes (unless technically required).
- [ ] All new fixtures are defined/imported in `conftest.py`.

## Additional Notes for Reviewers