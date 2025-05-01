# repo-prompt

An advanced developer productivity tool that connects local code context with LLM-based prompt generation and intelligent CLI integration. Inspired by Cursor AI, fully local and privacy-respecting.

## Features

- 🗺️ **CodeMap Generation**: Analyze and map your codebase structure
- 🤖 **Smart Prompt Generation**: Generate context-aware prompts based on your code
- 💬 **Interactive Chat**: Have conversations about your code with AI assistance
- 🔄 **Diff Application**: Apply code changes with intelligent context
- 🔍 **Ethical Audit**: Optional code auditing for ethical considerations

## Installation

```bash
# Clone the repository
git clone https://github.com/AykutAydin/repo-prompt.git
cd repo-prompt

# Create and activate virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with pip
pip install -e .

# Or install with Poetry (recommended)
poetry install
```

## Configuration

1. Create a `.env` file in your project root:
```env
OPENAI_API_KEY=sk-your-key-here
REPOPROMPT_CACHE_DIR=~/.repo_prompt/cache
```

2. Initialize repo-prompt:
```bash
repo-prompt init
```

## Usage

### Extract CodeMap
```bash
repo-prompt extract
```

### Generate Prompts
```bash
repo-prompt generate "Create a new API endpoint for user authentication"
```

### Interactive Chat
```bash
repo-prompt chat
```

### Apply Diffs
```bash
repo-prompt apply diff.patch
```

### Run Ethical Audit
```bash
repo-prompt audit
```

## Development

### Prerequisites
- Python 3.10+
- Poetry (recommended) or pip

### Setup Development Environment
```bash
# Clone the repository
git clone https://github.com/AykutAydin/repo-prompt.git
cd repo-prompt

# Install dependencies with Poetry
poetry install

# Activate virtual environment
poetry shell

# Run tests
pytest
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [Cursor AI](https://cursor.sh/)
- Built with [OpenAI GPT-4](https://openai.com/gpt-4)
- Uses [Typer](https://typer.tiangolo.com/) for CLI
- Thanks to all contributors!