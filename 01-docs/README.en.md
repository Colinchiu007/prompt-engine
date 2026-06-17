# Prompt Engine

An AI-powered image prompt optimization engine for Midjourney, Stable Diffusion, DALL·E, Flux, and more.

[![Tests](https://github.com/Colinchiu007/prompt-engine/actions/workflows/test.yml/badge.svg)](https://github.com/Colinchiu007/prompt-engine/actions)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

📖 Full user manual (Chinese): [docs/MANUAL.md](docs/MANUAL.md)

## What is Prompt Engine?

Prompt Engine transforms simple text descriptions into high-quality prompts optimized for specific AI image generation platforms. It supports **7 platforms**, **25 visual style dimensions**, **RAG-enhanced optimization**, and **3 integration modes** (Python SDK, REST API, CLI).

> Built for developers who need consistent, high-quality image prompts across multiple platforms.

## Features

| Feature | Description |
|---------|-------------|
| 🎯 **Multi-Platform** | Midjourney, Stable Diffusion, DALL·E, Flux, Tongyi, Wenyi, Jimeng |
| 🎨 **Style Engine** | 25-dimensional MJ style classifier (keyword + vector + LLM pipeline) |
| 📚 **RAG Knowledge Base** | 936 bilingual prompt cases for few-shot enhancement |
| 🔀 **A/B Candidates** | Generate multiple versions, pick the best |
| 📦 **Batch Processing** | Up to 10 prompts in a single request |
| ✍️ **Rewrite** | Short descriptions → 300-word detailed prompts |
| 🎲 **Disturb-Optimize** | Synonym/order perturbations for creative diversity |
| 👍 **Feedback Loop** | Thumbs up/down to tune keyword weights |
| 🔌 **3 Integration Modes** | Python SDK, REST API, MCP Server, CLI |
| 🖼️ **Web Dashboard** | Vue 3 + Element Plus dashboard with ECharts |
| 🏢 **Multi-LLM** | OpenAI, Xfyun (讯飞星火), Gemini |
| 📋 **DSL Templates** | `{option1\|option2}` / `__wildcard__` syntax |

## Quick Start

### 1. Via pip (future)

```bash
pip install prompt-engine-image
python -m prompt_engine.cli optimize --prompt "a cat" --platform midjourney
```

### 2. Via Docker

```bash
git clone https://github.com/Colinchiu007/prompt-engine.git
cd prompt-engine
docker-compose up -d
# Open http://localhost:8000
```

### 3. Via source

```bash
git clone https://github.com/Colinchiu007/prompt-engine.git
cd prompt-engine
pip install -r requirements.txt
python -m uvicorn prompt_engine.api.rest:app --port 8000
# Open http://localhost:8000
```

## CLI Usage

```bash
# Optimize a prompt
python -m prompt_engine.cli optimize --prompt "a cat" --platform midjourney

# Classify prompt style
python -m prompt_engine.cli classify --prompt "a majestic cat"

# List all style categories
python -m prompt_engine.cli categories

# Submit feedback
python -m prompt_engine.cli feedback --prompt "a cat" --result "A majestic feline..."

# Get recommendations
python -m prompt_engine.cli recommend --prompt "cat"
```

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/optimize` | Optimize a prompt |
| POST | `/v1/optimize/batch` | Batch optimize |
| POST | `/v1/classify` | Style classification |
| POST | `/v1/evaluate` | Evaluate optimization |
| POST | `/v1/rewrite` | Expand short prompt |
| POST | `/v1/disturb-optimize` | Disturb & optimize |
| POST | `/v1/reverse` | Image → prompt (vision) |
| POST | `/v1/feedback` | Submit feedback |
| GET | `/v1/keywords` | List keywords for platform |
| GET | `/v1/resources` | Engine resources |
| GET | `/v1/stats/overview` | Dashboard stats |

### Example

```python
import requests

resp = requests.post("http://localhost:8000/v1/optimize", json={
    "prompt": "a majestic cat",
    "platform": "midjourney"
})
print(resp.json()["optimized_prompt"])
# "A majestic feline with regal posture, glowing..."
```

## Web Dashboard

The built-in Vue 3 dashboard provides:

- **Workbench**: Optimize, classify, evaluate, rewrite, compare versions
- **Dashboard**: Stats cards, platform distribution, category distribution
- **Settings**: LLM provider / image model / wildcard configuration

![Dashboard screenshot placeholder]

## Platform Strategies

| Platform | Strategy |
|----------|----------|
| **Midjourney** | `--ar` parameters, style suffixes, quality control |
| **Stable Diffusion** | Weight syntax `(keyword:1.5)`, negative prompt |
| **DALL·E 3** | Natural language structure, short sentence format |
| **Tongyi Wanxiang** | Chinese idioms, poetic descriptions |
| **Wenyi Yige** | Keyword-based, four-character phrases |
| **Jimeng** | Visual impact, mood description |
| **Generic** | Cross-platform fallback |

## Architecture

```
User Input
    ↓
[Optimizer] ← [LLM Provider (OpenAI/Xfyun/Gemini)]
    ↓
[Strategy (7 platforms)] + [RAG Knowledge Base]
    ↓
[Keyword Injector] + [25-dim Classifier]
    ↓
[Post-process] + [Disturb-Optimize]
    ↓
Optimized Prompt
```

## Configuration

Create a `.env` file:

```env
# LLM Provider (choose one)
OPENAI_API_KEY=sk-...
XFYUN_APPID=...
GEMINI_API_KEY=...

# Image Generation (optional)
REPLICATE_API_KEY=r8_...
STABILITY_API_KEY=sk-...
```

Then start the server:

```bash
python -m uvicorn prompt_engine.api.rest:app --port 8000
```

## Version History

| Version | Highlights | Tests |
|---------|-----------|-------|
| v0.1-v0.5 | Core optimizer, 7 platforms, 25-dim classifier, CLI | 127 |
| v0.6-v0.7 | Agent Skill, RAG, DSL syntax, Web Dashboard | 177 |
| v0.8-v0.9 | Image preview, cache pool, Picsum Photos | 198 |
| v0.10 | Docker, CI, Batch UI | 212 |
| v0.11 | Style selector, keywords UI, rewrite UI | 203 |
| v0.12 | Feedback UI, A/B multi-version | 207 |
| **v0.13** | **English docs, PyPI config, GitHub badges** | **207** |

## Technology Stack

- **Backend**: Python 3.11, FastAPI, Pydantic
- **Frontend**: Vue 3, Element Plus, ECharts
- **Database**: Chroma (vector), JSON (feedback/weights)
- **Infrastructure**: Docker, GitHub Actions, Playwright (E2E)
- **Testing**: pytest, pytest-playwright (203 tests)

## Environment

- **OS**: Windows / Linux / macOS
- **Python**: 3.10+
- **Docker**: Optional (recommended for deployment)

## Contributing

1. Fork this repo
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Run tests (`pytest tests/ -q`)
4. Submit a Pull Request

Follow the coding conventions:
- Types for all public functions
- Tests for new features (TDD preferred)
- Update docs (CHANGELOG/README/PRD)

## License

MIT License. See [LICENSE](LICENSE) for details.

## Related Projects

- [awesome-gpt-image-2](https://github.com/YouMind-OpenLab/awesome-gpt-image-2) — GPT-Image2 prompt gallery
- [prompt-optimizer](https://github.com/YouMind-OpenLab/prompt-optimizer) — Multi-provider prompt optimization product
- [sd-dynamic-prompts](https://github.com/adieyal/sd-dynamic-prompts) — Dynamic prompt generation library (inspiration for DSL syntax)
- [Infinity](https://github.com/Yu-Fangxu/Infinity) — CVPR 2025 image generation model (inspiration for IVC/BSC/Rewriter)
- [Nano Banana Pro Prompts](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts) — 14K+ community prompt dataset
