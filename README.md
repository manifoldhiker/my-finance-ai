# Financial Agent

## Setup

1. **Install uv**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure environment**:
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your API tokens for Monobank and Wise.

## Usage

For development notebooks:
```bash
uv run jupyter notebook
```
