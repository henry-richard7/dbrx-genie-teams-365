"""Chart.js configuration generator using an LLM.

This module provides :class:`ChartJsGenerator`, which takes a tabular
dataset and prompts a language model to produce a fully-formed Chart.js
JSON configuration object for chart visualisation.
"""

import json
import logging
from os import environ

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from utils.llm_summarizer import LlmSummarizer
from utils.llm_client_base import BaseLLMClient

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_CHARTJS_PROMPT = """You are an expert at converting markdown tables into Chart.js JSON configuration objects. Your output must be raw JSON only — no code fences, no explanation, no preamble.

---

## STEP 1 — ANALYZE THE DATA

Examine the markdown table:
- Count the number of numeric columns (series).
- Count the number of rows (data points).
- Determine if x-axis values are dates, categories, or part-of-a-whole.
- Determine if there are multiple series (grouped/stacked) or a single series.

---

## STEP 2 — GENERATE CHART.JS CONFIGURATION

Create a JSON object that can be passed directly to the `data` and `options` properties of a new Chart instance:
```javascript
new Chart(ctx, {
    type: config.type,
    data: config.data,
    options: config.options
});
```

The JSON you output must exactly match the `config` object in the example above. It MUST have three top-level keys: `type`, `data`, and `options`.

### Guidelines:
- `type`: Can be "bar", "line", "pie", "doughnut". Use "bar" for vertical/horizontal bars (set `options.indexAxis = 'y'` for horizontal).
- `data.labels`: Array of strings for the X-axis (or Y-axis if horizontal).
- `data.datasets`: Array of objects. Each dataset needs a `label` and `data` (array of numbers).
- Use appealing and distinct colors for `backgroundColor` and `borderColor` in datasets. Use arrays of colors for pie/doughnut charts.
- Do NOT use Javascript functions or variables. ONLY use valid JSON (strings, numbers, booleans, arrays, objects, null).
- Keep `options.responsive` as true, and `options.maintainAspectRatio` as false.
- Ensure the title is set in `options.plugins.title`.

Example Structure:
{
  "type": "bar",
  "data": {
    "labels": ["Jan", "Feb", "Mar"],
    "datasets": [
      {
        "label": "Sales",
        "data": [10, 20, 30],
        "backgroundColor": "rgba(54, 162, 235, 0.5)"
      }
    ]
  },
  "options": {
    "responsive": true,
    "maintainAspectRatio": false,
    "plugins": {
      "title": { "display": true, "text": "Monthly Sales" }
    }
  }
}

---

## RULES

1. NEVER wrap output in ```json or any code fences.
2. Output ONLY the raw JSON. Nothing else.
3. Ensure numbers are unquoted in the JSON.
4. If multiple columns of data exist, map each numeric column to a separate dataset.
5. If a Gauge chart is requested or appropriate for a single KPI, simulate it using type: "doughnut" with `options: { circumference: 180, rotation: 270 }`.

---

## INPUT

A markdown table is provided below. Analyze it and output the correct Chart.js JSON configuration.
"""


class ChartJsGenerator(BaseLLMClient):
    """Generates Chart.js configuration JSON from tabular data using an LLM.

    Uses the same authentication pattern as :class:`~utils.llm_summarizer.LlmSummarizer`
    and caches model instances by credential scope to minimise token-fetch overhead.
    """

    def generate_chart_config(
        self,
        columns: list,
        data: list,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> dict | None:
        """Generates a complete Chart.js JSON configuration payload.

        Converts the dataset to a Markdown table, sends it to the configured LLM
        with the chart-generation system prompt, and parses the returned JSON.

        Args:
            columns (list): Column definitions — each must have a ``'name'`` key.
            data (list): Row data as a list of lists (same format as Genie SQL results).
            client_id (str | None): OAuth Client ID for a per-group Databricks workspace.
                Pass ``None`` to use global environment credentials.
            client_secret (str | None): OAuth Client Secret paired with ``client_id``.

        Returns:
            dict | None: A valid Chart.js config dict (``{"type": "...", "data": ...}``)
            or ``None`` if the LLM call fails or returns unparseable output.
        """
        table_text = LlmSummarizer.dataframe_to_text(columns, data)
        if not table_text:
            logger.debug(
                "chartjs_generator: empty table, skipping chart generation."
            )
            return None

        model = self._get_or_create_model(client_id, client_secret)
        if model is None:
            return None

        prompt = _CHARTJS_PROMPT + "\n" + table_text

        try:
            response = model.invoke(prompt)
            if hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
                usage = response.response_metadata["token_usage"]
                logger.info(f"ChartJsGenerator Token Usage - Input: {usage.get('prompt_tokens', 0)}, Output: {usage.get('completion_tokens', 0)}")
        except Exception as e:
            logger.warning(f"ChartJsGenerator LLM call failed: {e}")
            return None

        raw = self._parse_json_response(response)

        try:
            config = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"ChartJsGenerator: LLM returned invalid JSON. "
                f"First 300 chars: {raw[:300]}"
            )
            return None

        if not isinstance(config, dict) or "type" not in config or "data" not in config:
            logger.warning(
                "ChartJsGenerator: LLM JSON is not a valid Chart.js root object."
            )
            return None

        logger.debug("ChartJsGenerator: successfully generated chart config.")
        return config
