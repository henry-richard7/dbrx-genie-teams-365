"""Adaptive Card chart generator using an LLM.

This module provides :class:`AdaptiveCardChartGenerator`, which takes a tabular
dataset and prompts a language model to produce a fully-formed Microsoft Adaptive
Card JSON payload for chart visualisation — including richer chart types such as
``Chart.Line``, ``Chart.Gauge``, ``Chart.Pie``, and stacked variants that the
hand-coded :class:`AdaptiveCardTemplate` helpers cannot produce.
"""

import json
import logging
from os import environ

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from utils.llm_summarizer import LlmSummarizer

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_CHART_PROMPT = """You are an expert at converting markdown tables into Microsoft Adaptive Card JSON for chart visualization. Your output must be raw JSON only — no code fences, no explanation, no preamble.

---

## STEP 1 — ANALYZE THE DATA

Examine the markdown table:
- Count the number of numeric columns (series).
- Count the number of rows (data points).
- Determine if x-axis values are dates, categories, or part-of-a-whole.
- Determine if there are multiple series (grouped/stacked) or a single series.

---

## STEP 2 — SELECT THE BEST CHART TYPE

Use this decision logic:

| Condition | Chart Type |
|---|---|
| 1 category column + 1 value column, showing proportions | Chart.Pie |
| 1 category column + 1 value column, donut style preferred | Chart.Donut |
| 1 category + 1 value, horizontal comparison | Chart.HorizontalBar |
| 1 category + 1 value, vertical bars | Chart.VerticalBar |
| Multiple series over time or categories (side-by-side) | Chart.VerticalBar.Grouped |
| Multiple series over time or categories (stacked) | Chart.VerticalBar.Grouped with "stacked": true |
| Multiple series over time showing trends | Chart.Line |
| Multiple series in horizontal stacked rows | Chart.HorizontalBar.Stacked |
| Single KPI value with risk/status segments | Chart.Gauge |

---

## STEP 3 — GENERATE THE CORRECT JSON

Use the exact schema below for the selected chart type. Do NOT mix schemas between types.

---

### SCHEMA A — Chart.Pie and Chart.Donut
Used when: single series, proportional data (parts of a whole).
Data format: each item uses "legend" (string) and "value" (number).

{
  "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Chart.Pie",
      "title": "<Chart Title>",
      "colorSet": "categorical",
      "data": [
        { "legend": "<Category>", "value": <number> }
      ]
    }
  ]
}

Replace "Chart.Pie" with "Chart.Donut" for donut style.

---

### SCHEMA B — Chart.VerticalBar and Chart.HorizontalBar
Used when: single series, simple category-vs-value comparison.
Data format: each item uses "x" (string) and "y" (number).

{
  "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Chart.VerticalBar",
      "title": "<Chart Title>",
      "xAxisTitle": "<X Axis Label>",
      "yAxisTitle": "<Y Axis Label>",
      "colorSet": "categorical",
      "data": [
        { "x": "<Category>", "y": <number> }
      ]
    }
  ]
}

Replace "Chart.VerticalBar" with "Chart.HorizontalBar" for horizontal layout.
For Chart.HorizontalBar, you may also set "displayMode": "AbsoluteWithAxis" | "AbsoluteNoAxis" | "PartToWhole".

---

### SCHEMA C — Chart.Line and Chart.VerticalBar.Grouped
Used when: multiple series with shared x-axis (time or categories).
Data format: each series has "legend" (string) and "values" array of {x, y} objects.

{
  "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Chart.Line",
      "title": "<Chart Title>",
      "xAxisTitle": "<X Axis Label>",
      "yAxisTitle": "<Y Axis Label>",
      "colorSet": "categorical",
      "data": [
        {
          "legend": "<Series Name>",
          "values": [
            { "x": "<x label>", "y": <number> }
          ]
        }
      ]
    }
  ]
}

Replace "Chart.Line" with "Chart.VerticalBar.Grouped" for grouped bars.
For stacked grouped bars, add "stacked": true to the chart element.

---

### SCHEMA D — Chart.HorizontalBar.Stacked
Used when: multiple series shown as horizontal stacked rows per category.
Data format: outer array has "title" per row; inner "data" array has "legend", "value", and optional "color".

{
  "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Chart.HorizontalBar.Stacked",
      "title": "<Chart Title>",
      "data": [
        {
          "title": "<Row Label>",
          "data": [
            { "legend": "<Segment Label>", "value": <number>, "color": "good" }
          ]
        }
      ]
    }
  ]
}

Allowed "color" values: good, warning, attention, neutral, categoricalRed, categoricalPurple,
categoricalLavender, categoricalBlue, categoricalLightBlue, categoricalTeal, categoricalGreen,
categoricalLime, categoricalMarigold, sequential1-sequential8, divergingBlue, divergingLightBlue,
divergingCyan, divergingTeal, divergingYellow, divergingPeach, divergingLightRed, divergingRed,
divergingMaroon, divergingGray.

---

### SCHEMA E — Chart.Gauge
Used when: a single KPI or score value with risk/status segments (e.g. low/medium/high).
Requires a "value" (current value) and "segments" array defining ranges.

{
  "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Chart.Gauge",
      "title": "<Chart Title>",
      "value": <current number>,
      "valueFormat": "Percentage",
      "segments": [
        { "legend": "<Low Label>", "size": <number>, "color": "good" },
        { "legend": "<Mid Label>", "size": <number>, "color": "warning" },
        { "legend": "<High Label>", "size": <number>, "color": "attention" }
      ]
    }
  ]
}

"valueFormat" options: "Percentage" or "Fraction".
Segment sizes must sum to 100.

---

## RULES

1. NEVER use Chart.js properties: backgroundColor, borderColor, datasets, labels, options, scales, responsive, plugins.
2. NEVER wrap output in ```json or any code fences.
3. "x" must always be a string. "y" must always be a raw number (no quotes, no commas, no units).
4. "value" in Pie/Donut/Stacked schemas must be a raw number.
5. Infer "title", "xAxisTitle", and "yAxisTitle" directly from the markdown table headers.
6. Use "colorSet": "categorical" for most charts. Use "diverging" for comparisons. Use "sequential" for ordered/ranked data.
7. Always use schema version "1.5".
8. Always include "$schema": "https://adaptivecards.io/schemas/adaptive-card.json".
9. Output ONLY the raw JSON. Nothing else.

---

## INPUT

A markdown table is provided below. Analyze it and output the correct Adaptive Card JSON.
"""


class AdaptiveCardChartGenerator:
    """Generates Adaptive Card chart JSON from tabular data using an LLM.

    Uses the same authentication pattern as :class:`~utils.llm_summarizer.LlmSummarizer`
    and caches model instances by credential scope to minimise token-fetch overhead.
    """

    def __init__(self) -> None:
        """Initialises the generator with empty model and workspace client caches."""
        self._models: dict = {}
        self._workspace_clients: dict = {}

    def generate_chart_card(
        self,
        columns: list,
        data: list,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> dict | None:
        """Generates a complete Adaptive Card JSON payload for chart visualisation.

        Converts the dataset to a Markdown table, sends it to the configured LLM
        with the chart-generation system prompt, and parses the returned JSON.

        Args:
            columns (list): Column definitions — each must have a ``'name'`` key.
            data (list): Row data as a list of lists (same format as Genie SQL results).
            client_id (str | None): OAuth Client ID for a per-group Databricks workspace.
                Pass ``None`` to use global environment credentials.
            client_secret (str | None): OAuth Client Secret paired with ``client_id``.

        Returns:
            dict | None: A valid Adaptive Card dict (``{"type": "AdaptiveCard", ...}``)
            or ``None`` if the LLM call fails or returns unparseable output.
        """
        table_text = LlmSummarizer.dataframe_to_text(columns, data)
        if not table_text:
            logger.debug("chart_card_generator: empty table, skipping chart generation.")
            return None

        model = self._get_or_create_model(client_id, client_secret)
        if model is None:
            return None

        prompt = _CHART_PROMPT + "\n" + table_text

        try:
            response = model.invoke(prompt)
        except Exception as e:
            logger.warning(f"AdaptiveCardChartGenerator LLM call failed: {e}")
            return None

        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw.strip()

        # Strip markdown code fences if the LLM adds them despite instructions
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            card = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"AdaptiveCardChartGenerator: LLM returned invalid JSON. "
                f"First 300 chars: {raw[:300]}"
            )
            return None

        if not isinstance(card, dict) or card.get("type") != "AdaptiveCard":
            logger.warning(
                "AdaptiveCardChartGenerator: LLM JSON is not a valid AdaptiveCard root object."
            )
            return None

        logger.debug("AdaptiveCardChartGenerator: successfully generated chart card.")
        return card

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create_model(
        self, client_id: str | None, client_secret: str | None
    ) -> ChatOpenAI | None:
        """Returns a cached (or newly created) ChatOpenAI instance for the given scope."""
        llm_endpoint = environ.get(
            "OPENAI_MODEL_NAME", "databricks-qwen3-next-80b-a3b-instruct"
        )
        cache_key = client_id or "default"

        if cache_key in self._models:
            return self._models[cache_key]

        kwargs: dict = {
            "model": llm_endpoint,
            "temperature": 0.0,  # deterministic JSON output
        }

        base_url = environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

        kwargs["api_key"] = environ.get("OPENAI_API_KEY")

        if not kwargs["api_key"] or kwargs["api_key"] == "not-provided":
            logger.debug(
                "AdaptiveCardChartGenerator: no OPENAI_API_KEY, "
                "attempting Databricks WorkspaceClient token."
            )
            from databricks.sdk import WorkspaceClient

            host = environ.get("DATABRICKS_HOST")
            try:
                if cache_key not in self._workspace_clients:
                    if client_id and client_secret:
                        self._workspace_clients[cache_key] = WorkspaceClient(
                            host=host,
                            client_id=client_id,
                            client_secret=client_secret,
                        )
                    else:
                        self._workspace_clients[cache_key] = WorkspaceClient(host=host)

                w = self._workspace_clients[cache_key]
                creds = w.config.authenticate()
                if creds and isinstance(creds, dict) and "Authorization" in creds:
                    kwargs["api_key"] = creds["Authorization"].replace("Bearer ", "")
                elif w.config.token:
                    kwargs["api_key"] = w.config.token

                if "base_url" not in kwargs and host:
                    kwargs["base_url"] = f"{host.rstrip('/')}/serving-endpoints"
            except Exception as exc:
                logger.error(
                    f"AdaptiveCardChartGenerator: failed to obtain Databricks token: {exc}"
                )

        if not kwargs.get("api_key"):
            kwargs["api_key"] = "not-provided"

        try:
            self._models[cache_key] = ChatOpenAI(**kwargs)
            return self._models[cache_key]
        except Exception as exc:
            logger.error(
                f"AdaptiveCardChartGenerator: failed to create ChatOpenAI model: {exc}"
            )
            return None
