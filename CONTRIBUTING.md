# Contributing to Databricks Genie Teams Bot

First off, thank you for considering contributing to the Databricks Genie Teams Bot! It's people like you that make open-source software such a great community.

## Where do I go from here?

If you've noticed a bug or have a feature request, please make one! It's generally best if you get confirmation of your bug or approval for your feature request this way before starting to code.

## Fork & create a branch

If this is something you think you can fix, then fork the repository and create a branch with a descriptive name.

A good branch name would be (where issue #325 is the ticket you're working on):
```sh
git checkout -b 325-add-new-chart-type
```

## Get the test suite running

Make sure you have `uv` or standard Python `venv` set up, as described in the README.
We use `pytest` for all unit and integration testing, relying heavily on `pytest-asyncio` and `pytest-mock`. 

To run the full test suite locally, execute:
```sh
uv run pytest -v
```

> [!NOTE]
> For detailed instructions on writing tests, mocking external services, and dealing with `asyncio`, please refer to our **[Testing Guide](TESTING.md)**.

Ensure your code passes the local build and tests before pushing.

## Code Style & Conventions

To maintain a high quality and readable codebase, please adhere to the following guidelines:

1. **Google-Style Docstrings:** All new modules, classes, and complex functions MUST be documented using Google-style docstrings. This ensures consistent API documentation.
2. **Type Hinting:** We heavily utilize Python type hints (`typing`). Please ensure your additions are fully typed.
3. **Async Everything:** This bot relies on `FastAPI` and `asyncio` to remain non-blocking and scalable. When interacting with APIs or databases, always use asynchronous libraries (like `aiohttp`, `aiosqlite`, `asyncpg`) and the `async/await` syntax.
4. **Graceful Error Handling:** Always wrap your logic in `try/except` blocks where failures might occur, and consider the user experience. Do not let exceptions crash the bot silently; instead, return a friendly Adaptive Card error message if something fails.

## Implementing New Features

### Adding a New Teams Command
If you are adding a new text command that the bot should respond to:
1. Update `handlers/message_handler.py`.
2. Add the specific routing logic.
3. Ensure any state transitions or required session variables are handled correctly in the database.

### Adding New Visualizations
If you are adding a new chart type (e.g., Line charts or Scatter plots):
1. Create the new Adaptive Card template inside `modules/AdaptiveCardTemplate.py`.
2. Update the `llm_summarizer.py` prompts so the LLM knows the new chart type is available.

## Pull Request Process

1. Ensure any install or build dependencies are removed before the end of the layer when doing a build.
2. Update the README.md with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations and container parameters.
3. You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.

Thank you for contributing!
