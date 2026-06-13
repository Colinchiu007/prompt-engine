---
name: prompt-engine
description: Image-generation prompt optimization engine - optimize, classify, and recommend prompts for Midjourney, Stable Diffusion, DALL·E, and more
---

# Prompt Engine — Image Prompt Optimization Engine

Optimize, classify, and analyze image-generation prompts across 7 platforms.

## Quick Start

```python
from prompt_engine import Optimizer, OptimizeRequest, PlatformType

optimizer = Optimizer()
result = optimizer.optimize(OptimizeRequest(
    prompt="a cat sitting on a windowsill",
    platform=PlatformType.MIDJOURNEY,
))
print(result.optimized_prompt)
```

## CLI Commands

```bash
# Style classification (25 MJ dimensions)
prompt-engine classify "watercolor painting of mountains"

# List all 25 style dimensions
prompt-engine categories

# Optimize prompt for a platform
prompt-engine optimize "a cat" -p midjourney -c 7

# Recommend categories for a style
prompt-engine recommend oil_painting

# Submit classification feedback
prompt-engine feedback "a cat" -d lighting nature_and_animals -r 4 -m keyword_match

# View feedback stats
prompt-engine feedback --stats
```

## Available Tools

- `classify_style` — Classify prompt into 25 MJ style dimensions
- `optimize_prompt` — Optimize prompt for target platform
- `list_style_categories` — List all style dimensions with descriptions

## Style Classification Pipeline

```
prompt → keyword_match (0ms, exact) → vector_rag (50ms, semantic) → llm_classify (1s, fallback)
```

## Reference

- 25 MJ style dimensions: lighting, material_properties, colors_and_palettes, camera, nature_and_animals, drawing_and_art_mediums, etc.
- 7 platforms: midjourney, stable_diffusion, dalle, tongyi, yizhang, jimeng, generic
- 14 style types: realistic, anime, oil_painting, watercolor, cyberpunk, etc.

See `references/api-reference.md` for all REST API endpoints.
See `references/style-library.md` for the 25-dimension style table.
See `references/cli-commands.md` for all CLI subcommands.
