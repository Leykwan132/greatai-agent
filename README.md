https://greataihackathon.com/

# GreatAI Backend - Agent

This repository contains the backend implementation for building voice AI applications using LiveKit Agents. It provides a foundational setup for integrating voice AI capabilities with various tools and frameworks.

## Features

- Python-based backend framework.
- Centralized tool management for AI agents.
- Integration with LiveKit Cloud for enhanced noise cancellation and speaker detection.
- Compatibility with multiple frontend platforms and telephony systems.

## Project Structure

```
credentials.json       # Sensitive credentials (ignored in .gitignore)
token.json             # Token storage (ignored in .gitignore)
pyproject.toml         # Project metadata and dependencies
README.md              # Project documentation
taskfile.yaml          # Task automation configuration
Dockerfile             # Docker configuration for containerization
src/                   # Source code directory
    agent.py           # Core agent implementation
tests/                 # Test cases for the project
    test_agent.py      # Unit tests for agent.py
```

## Getting Started

### Prerequisites

- Python 3.10 or higher.
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### Running the Application

Run the main script:

```bash
python src/agent.py
```

### Running Tests

Execute the test suite:

```bash
pytest tests/
```

## Contributing

Fork the repository and submit pull requests for contributions.

## License

This project is licensed under the MIT License. Refer to the `LICENSE` file for details.

---

For more information, visit [LiveKit Agents Documentation](https://docs.livekit.io/agents/).
